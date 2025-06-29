"""
PTT 爬蟲 Celery 任務
將原有的 PTT 爬蟲邏輯轉換為分散式任務
"""
import collections
import datetime
import os
import random
import time
import urllib.parse
import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
from sqlalchemy import create_engine, BigInteger, Column, Date, Float, MetaData, String, Table, Text, Integer
from sqlalchemy.dialects.mysql import insert
from crawler.config import (
    MYSQL_ACCOUNT, MYSQL_HOST, MYSQL_PASSWORD, MYSQL_PORT, MYSQL_DATABASE,
    PTT_BOARD, PTT_DELAY_MIN, PTT_DELAY_MAX, PTT_TIMEOUT
)
from crawler.worker import app


# PTT 爬蟲相關的類別和函數 (移植自原本的 ptt_crawler.py)

# 自定義例外類別
class Error(Exception):
    """此模組拋出的所有例外的基礎類別"""
    pass

class InValidBeautifulSoupTag(Error):
    """因為無效的 BeautifulSoup 標籤而無法建立 ArticleSummary"""
    pass

class NoGivenURLForPage(Error):
    """建立頁面時給定了 None 或空白的 URL"""
    pass

class PageNotFound(Error):
    """無法透過給定的 URL 取得頁面"""
    pass

class ArtitcleIsRemoved(Error):
    """無法從 ArticleSummary 讀取已被刪除的文章"""
    pass


# 工具函數
def parse_std_url(url):
    """解析標準的 PTT URL"""
    prefix, _, basename = url.rpartition('/')
    basename, _, _ = basename.rpartition('.')
    bbs, _, board = prefix.rpartition('/')
    bbs = bbs[1:]
    return bbs, board, basename


def parse_title(title):
    """解析文章標題以獲取更多資訊"""
    isreply = 'Re:' in title
    isforward = 'Fw:' in title
    
    start_bracket = title.find('[')
    if start_bracket == -1:
        return '無分類', isreply, isforward
    
    end_bracket = title.find(']', start_bracket)
    if end_bracket == -1:
        return '無分類', isreply, isforward
    
    category = title[start_bracket + 1:end_bracket].strip()
    
    if not category:
        return '無分類', isreply, isforward
    
    return category, isreply, isforward


def parse_username(full_name):
    """解析用戶名稱以獲取其用戶帳號和暱稱"""
    if ' (' not in full_name:
        return full_name, ''
    name, nickname = full_name.split(' (', 1)
    nickname = nickname.rstrip(')')
    return name, nickname


# Msg 是一個 namedtuple，用於模型化推文的資訊
Msg = collections.namedtuple('Msg', ['type', 'user', 'content', 'ipdatetime'])


class ArticleSummary:
    """用於模型化文章資訊的類別，該資訊來自 ArticleListPage"""

    def __init__(self, title, url, score, date, author, mark, removeinfo):
        # 標題
        self.title = title
        self.category, self.isreply, self.isforward = parse_title(title)

        # URL
        self.url = url
        _, self.board, self.aid = parse_std_url(url)

        # 元資料
        self.score = score
        self.date = date
        self.author = author
        self.mark = mark

        # 刪除資訊
        self.isremoved = True if removeinfo else False
        self.removeinfo = removeinfo

    @classmethod
    def from_bs_tag(cls, tag):
        """從對應的 bs 標籤建立 ArticleSummary 物件的類別方法"""
        try:
            removeinfo = None
            title_tag = tag.find('div', class_='title')
            a_tag = title_tag.find('a')

            if not a_tag:
                removeinfo = title_tag.get_text().strip()

            if not removeinfo:
                title = a_tag.get_text().strip()
                url = a_tag.get('href').strip()
                score = tag.find('div', class_='nrec').get_text().strip()
            else:
                title = '本文章已被刪除'
                url = ''
                score = ''

            date = tag.find('div', class_='date').get_text().strip()
            author = tag.find('div', class_='author').get_text().strip()
            mark = tag.find('div', class_='mark').get_text().strip()
        except Exception:
            raise InValidBeautifulSoupTag(tag)

        return cls(title, url, score, date, author, mark, removeinfo)

    def __repr__(self):
        return '<Summary of Article("{}")>'.format(self.url)

    def __str__(self):
        return self.title

    def read(self):
        """從 URL 讀取文章並返回 ArticlePage"""
        if self.isremoved:
            raise ArtitcleIsRemoved(self.removeinfo)
        return ArticlePage(self.url)


class Page:
    """頁面的基礎類別"""
    ptt_domain = 'https://www.ptt.cc'

    def __init__(self, url):
        if not url:
            raise NoGivenURLForPage

        self.url = url
        url = urllib.parse.urljoin(self.ptt_domain, self.url)
        
        # 使用 fake-useragent 和 1 秒超時
        try:
            ua = UserAgent()
            user_agent = ua.random
        except:
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        
        resp = requests.get(
            url=url, 
            cookies={'over18': '1'}, 
            verify=True, 
            timeout=PTT_TIMEOUT,
            headers={'User-Agent': user_agent}
        )

        if resp.status_code == requests.codes.ok:
            self.html = resp.text
        else:
            raise PageNotFound(f"HTTP {resp.status_code}")


class ArticleListPage(Page):
    """用於模型化文章列表頁面的類別"""

    def __init__(self, url):
        super().__init__(url)

        # 設定文章標籤
        soup = BeautifulSoup(self.html, 'html.parser')
        self.article_summary_tags = soup.find_all('div', 'r-ent')
        self.article_summary_tags.reverse()

        # 設定相關 URL
        action_tags = soup.find('div', class_='action-bar').find_all('a')
        self.related_urls = {}
        url_names = 'board man oldest previous next newest'
        for idx, name in enumerate(url_names.split()):
            self.related_urls[name] = action_tags[idx].get('href')

        # 設定版面和索引
        _, self.board, basename = parse_std_url(url)
        _, _, idx = basename.partition('index')
        if idx:
            self.idx = int(idx)
        else:
            _, self.board, basename = parse_std_url(self.related_urls['previous'])
            _, _, idx = basename.partition('index')
            self.idx = int(idx)+1

    @classmethod
    def from_board(cls, board, index=''):
        """從給定的版名和索引建立 ArticleListPage 物件的類別方法"""
        url = '/'.join(['/bbs', board, 'index'+str(index)+'.html'])
        return cls(url)

    def __repr__(self):
        return 'ArticleListPage("{}")'.format(self.url)

    def __iter__(self):
        return self.article_summaries

    def get_article_summary(self, index):
        return ArticleSummary.from_bs_tag(self.article_summary_tags[index])

    @property
    def article_summaries(self):
        return (ArticleSummary.from_bs_tag(tag) for tag in self.article_summary_tags)

    @property
    def previous(self):
        return ArticleListPage(self.related_urls['previous'])

    @property
    def next(self):
        return ArticleListPage(self.related_urls['next'])

    @property
    def oldest(self):
        return ArticleListPage(self.related_urls['oldest'])

    @property
    def newest(self):
        return ArticleListPage(self.related_urls['newest'])


class ArticlePage(Page):
    """用於模型化文章頁面的類別"""

    def __init__(self, url):
        super().__init__(url)
        self.soup = BeautifulSoup(self.html, 'html.parser')

        # 設定基本資訊
        _, self.board, self.aid = parse_std_url(url)
        self.url = url

        # 設定文章作者、標題和時間
        main_content = self.soup.find('div', id='main-content')
        metas = main_content.find_all('div', class_='article-metaline')

        try:
            self.author = metas[0].find('span', class_='article-meta-value').get_text()
            self.title = metas[1].find('span', class_='article-meta-value').get_text()
            self.datetime_str = metas[2].find('span', class_='article-meta-value').get_text()
            self.datetime = datetime.datetime.strptime(self.datetime_str, '%a %b %d %H:%M:%S %Y')
            self.date = self.datetime_str
        except (IndexError, ValueError):
            self.author = ''
            self.title = ''
            self.datetime_str = ''
            self.datetime = None
            self.date = ''

        # 解析標題分類
        self.category, self.isreply, self.isforward = parse_title(self.title)

        # 重要：先設定推文（在移除推文標籤之前）
        self.pushes = PushesHandler(self.soup)

        # 設定文章內容（這會移除推文標籤）
        self._set_content()

        # 設定文章 IP
        self._set_ip()

    def _set_content(self):
        """設定文章內容"""
        main_content = self.soup.find('div', id='main-content')
        
        # 移除 metaline
        for meta in main_content.find_all('div', class_='article-metaline'):
            meta.extract()
        for meta in main_content.find_all('div', class_='article-metaline-right'):
            meta.extract()
        
        # 移除推文
        for push in main_content.find_all('div', class_='push'):
            push.extract()
            
        self.content = main_content.get_text().strip()

    def _set_ip(self):
        """設定文章 IP"""
        try:
            ip_tag = self.soup.find('span', class_='f2')
            if ip_tag:
                ip_text = ip_tag.get_text()
                # 尋找 IP 位址格式
                import re
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', ip_text)
                if ip_match:
                    self.ip = ip_match.group(1)
                else:
                    self.ip = ''
            else:
                self.ip = ''
        except:
            self.ip = ''

    def __repr__(self):
        return 'ArticlePage("{}")'.format(self.url)


class PushesHandler:
    """用於處理推文的類別"""

    def __init__(self, soup):
        self.soup = soup
        self.pushes = self._parse_pushes()
        self.count = self._count_pushes()
        self.simple_expression = self._simple_expression()

    def _parse_pushes(self):
        """解析推文"""
        pushes = []
        push_tags = self.soup.find_all('div', class_='push')
        
        for push_tag in push_tags:
            try:
                push_type = push_tag.find('span', class_='push-tag').get_text().strip()
                push_user = push_tag.find('span', class_='push-userid').get_text().strip()
                push_content = push_tag.find('span', class_='push-content').get_text().strip()
                push_ipdatetime = push_tag.find('span', class_='push-ipdatetime').get_text().strip()
                
                pushes.append(Msg(push_type, push_user, push_content, push_ipdatetime))
            except:
                continue
                
        return pushes

    def _count_pushes(self):
        """計算推文數量"""
        count = {'all': 0, 'like': 0, 'boo': 0, 'neutral': 0}
        
        for push in self.pushes:
            count['all'] += 1
            if '推' in push.type:
                count['like'] += 1
            elif '噓' in push.type:
                count['boo'] += 1
            else:
                count['neutral'] += 1
                
        count['score'] = count['like'] - count['boo']
        return count

    def _simple_expression(self):
        """簡化的推文表達"""
        return [f"{push.type} {push.user}: {push.content}" for push in self.pushes]


# 全域只建立一次 engine、metadata、table 並 create_all
address = f"mysql+pymysql://{MYSQL_ACCOUNT}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DATABASE}"
engine = create_engine(address)
metadata = MetaData()

# PTT 文章資料表結構
ptt_articles_table = Table(
    "ptt_articles",
    metadata,
    Column("aid", String(20), primary_key=True),  # 文章編碼作為主鍵
    Column("board", String(50)),  # 版名
    Column("author", String(100)),  # 作者
    Column("title", String(500)),  # 標題
    Column("category", String(100)),  # 分類
    Column("content", Text),  # 內文
    Column("date", String(100)),  # 日期（原始格式）
    Column("ip", String(50)),  # IP位置
    Column("pushes_all", Integer),  # 總留言數
    Column("pushes_like", Integer),  # 推
    Column("pushes_boo", Integer),  # 噓
    Column("pushes_neutral", Integer),  # 中立
    Column("pushes_score", Integer),  # 文章分數
    Column("url", String(200)),  # 文章 URL
    Column("crawl_time", Date),  # 爬取時間
)

def init_database():
    """初始化資料庫，建立資料表"""
    try:
        metadata.create_all(engine)
        print("PTT 文章資料表已初始化")
        return True
    except Exception as e:
        print(f"初始化資料庫失敗: {e}")
        return False


def upload_ptt_data_to_mysql(df: pd.DataFrame):
    """將 PTT 文章資料上傳到 MySQL 資料庫"""
    if df.empty:
        print("無資料需要上傳")
        return 0

    print(f"準備上傳 {len(df)} 筆 PTT 文章資料到 MySQL...")

    # 準備資料
    df_copy = df.copy()
    df_copy['crawl_time'] = datetime.date.today()
    
    # 確保所有必要欄位存在
    required_columns = {
        'aid': '',
        'board': PTT_BOARD,
        'author': '',
        'title': '',
        'category': '無分類',
        'content': '',
        'date': '',
        'ip': '',
        'pushes_all': 0,
        'pushes_like': 0,
        'pushes_boo': 0,
        'pushes_neutral': 0,
        'pushes_score': 0,
        'url': ''
    }
    
    for col, default_value in required_columns.items():
        if col not in df_copy.columns:
            # 如果欄位完全不存在，才添加並設為默認值
            df_copy[col] = default_value
        else:
            # 對於存在的欄位，只填充真正的空值，但保留數值 0
            if col.startswith('pushes_'):
                # 對於推文相關欄位，只填充 None 和 NaN，保留數值 0
                df_copy[col] = df_copy[col].fillna(default_value)
                # 確保是整數類型
                df_copy[col] = df_copy[col].astype(int)
            else:
                # 對於其他欄位，正常填充空值
                df_copy[col] = df_copy[col].fillna(default_value)

    # 只保留需要的欄位
    df_copy = df_copy[list(required_columns.keys()) + ['crawl_time']]
    
    # ===== DEBUG: 輸出要送到資料庫的資料內容 =====
    print("=" * 80)
    print("🔍 DEBUG: 準備上傳到資料庫的資料:")
    print(f"📊 資料筆數: {len(df_copy)}")
    print(f"📋 欄位名稱: {list(df_copy.columns)}")
    print("📝 資料內容:")
    for idx, row in df_copy.iterrows():
        print(f"  第 {idx+1} 筆:")
        for col, value in row.items():
            if col == 'content':
                # content 可能很長，只顯示前50字
                content_preview = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
                print(f"    {col}: {content_preview}")
            else:
                print(f"    {col}: {value}")
        print("-" * 40)
    print("=" * 80)
    # ===== END DEBUG =====

    try:
        # 使用 MySQL 的 ON DUPLICATE KEY UPDATE 來處理重複資料
        with engine.connect() as conn:
            with conn.begin():  # 使用事務
                data_dict = df_copy.to_dict('records')
                
                # 使用 MySQL 的 INSERT ... ON DUPLICATE KEY UPDATE
                stmt = insert(ptt_articles_table).values(data_dict)
                
                # 定義更新的欄位（除了主鍵 aid）
                update_dict = {
                    col.name: stmt.inserted[col.name] 
                    for col in ptt_articles_table.columns 
                    if col.name != 'aid'
                }
                
                stmt = stmt.on_duplicate_key_update(**update_dict)
                result = conn.execute(stmt)
                
                print(f"成功處理 {len(data_dict)} 筆 PTT 文章資料（新增或更新）")
                return len(data_dict)
            
    except Exception as e:
        print(f"上傳 PTT 文章資料時發生錯誤：{e}")
        return 0


def ptt_crawl_single_page(board_name, page_index, target_date=None):
    """爬取單一頁面的文章資料"""
    print(f'正在處理 {board_name} 版第 {page_index} 頁')
    
    error_count = 0
    success_count = 0
    
    try:
        # 抓該板頁面的文章
        latest_page = ArticleListPage.from_board(board_name, page_index)
    except Exception as e:
        print(f'無法載入頁面 {page_index}，錯誤: {e}')
        return pd.DataFrame(), False

    # 準備資料收集的列表
    ptt_aid = []
    ptt_author = []
    ptt_board = []
    ptt_category = []
    ptt_title = []
    ptt_content = []
    ptt_url = []
    ptt_date = []
    ptt_ip = []
    ptt_all = []
    ptt_boo = []
    ptt_like = []
    ptt_neutral = []
    ptt_score = []
    ptt_comment = []

    should_stop = False
    old_articles_count = 0

    for summary in latest_page:
        if summary.isremoved:
            continue

        print(f'正在抓資料中...{summary.title[:50]}...')
        
        # 隨機延遲
        delay = random.uniform(PTT_DELAY_MIN, PTT_DELAY_MAX)
        time.sleep(delay)

        try:
            article = summary.read()
            
            # 如果有設定目標日期，檢查文章日期
            if target_date and article.datetime:
                if article.datetime < target_date:
                    old_articles_count += 1
                    print(f'📅 文章日期過舊：{article.datetime.strftime("%Y-%m-%d %H:%M")}，跳過')
                    if old_articles_count >= 10:
                        print(f'📅 發現連續 {old_articles_count} 篇過舊文章，停止爬取此頁')
                        should_stop = True
                    continue
                else:
                    old_articles_count = 0
            
            # 收集文章資料
            ptt_aid.append(article.aid)
            ptt_author.append(article.author)
            ptt_board.append(article.board)
            ptt_category.append(article.category)
            ptt_title.append(article.title)
            ptt_content.append(article.content)
            ptt_url.append(article.url)
            ptt_date.append(article.date)
            ptt_ip.append(article.ip)
            
            # 安全地收集推文數據，避免 NaN 值
            try:
                if hasattr(article, 'pushes') and article.pushes is not None:
                    # 直接嘗試獲取推文數據
                    count_data = getattr(article.pushes, 'count', None)
                    if count_data is not None and isinstance(count_data, dict):
                        # 成功獲取推文統計
                        ptt_all.append(count_data.get('all', 0))
                        ptt_boo.append(count_data.get('boo', 0))
                        ptt_like.append(count_data.get('like', 0))
                        ptt_neutral.append(count_data.get('neutral', 0))
                        ptt_score.append(count_data.get('score', 0))
                        ptt_comment.append(getattr(article.pushes, 'simple_expression', []))
                        print(f"✅ 推文數據: 總 {count_data.get('all', 0)}, 推 {count_data.get('like', 0)}, 噓 {count_data.get('boo', 0)}")
                    else:
                        # pushes 對象存在但 count 無效
                        raise ValueError("pushes.count 數據無效")
                else:
                    # article.pushes 不存在或為 None
                    raise ValueError("article.pushes 不存在")
            except Exception as push_error:
                # 如果推文數據獲取失敗，使用默認值
                ptt_all.append(0)
                ptt_boo.append(0)
                ptt_like.append(0)
                ptt_neutral.append(0)
                ptt_score.append(0)
                ptt_comment.append([])
                print(f"⚠️ 推文數據獲取失敗，使用默認值 0: {str(push_error)}")

            success_count += 1

        except Exception as e:
            error_count += 1
            article_title = summary.title if hasattr(summary, 'title') and summary.title else 'unknown'
            print(f'處理文章時發生錯誤: {article_title[:30]}... - {str(e)[:100]}')
            
            # 重要：即使發生錯誤，也要添加占位數據以保持列表長度一致
            # 這些數據會在後續被過濾掉
            ptt_aid.append('')  # 空字符串，會被過濾
            ptt_author.append('')
            ptt_board.append(board_name)
            ptt_category.append('')
            ptt_title.append('')  # 空標題，會被過濾掉
            ptt_content.append('')
            ptt_url.append('')
            ptt_date.append('')
            ptt_ip.append('')
            ptt_all.append(0)  # 占位數據
            ptt_boo.append(0)
            ptt_like.append(0)
            ptt_neutral.append(0)
            ptt_score.append(0)
            ptt_comment.append([])
            print(f"📝 添加占位數據以保持列表一致性（將被過濾）")
            
            continue

    # 建立 DataFrame（使用英文欄位名稱，對應資料庫結構）
    print(f"\n📊 準備建立 DataFrame:")
    print(f"  列表長度檢查:")
    print(f"    ptt_aid: {len(ptt_aid)}")
    print(f"    ptt_all: {len(ptt_all)}")
    print(f"    ptt_like: {len(ptt_like)}")
    print(f"    ptt_boo: {len(ptt_boo)}")
    print(f"    ptt_neutral: {len(ptt_neutral)}")
    
    dic = {
        'aid': ptt_aid,
        'author': ptt_author,
        'board': ptt_board,
        'category': ptt_category,
        'title': ptt_title,
        'content': ptt_content,
        'date': ptt_date,
        'ip': ptt_ip,
        'pushes_all': ptt_all,
        'pushes_boo': ptt_boo,
        'pushes_like': ptt_like,
        'pushes_neutral': ptt_neutral,
        'pushes_score': ptt_score,
        'url': ptt_url  # 使用收集的 URL 列表
    }
    
    final_data = pd.DataFrame(dic)
    print(f"📋 DataFrame 建立完成，原始數據: {len(final_data)} 筆")
    
    # 顯示推文數據統計
    print(f"📈 推文數據統計:")
    print(f"  推文數 > 0 的文章: {len(final_data[final_data['pushes_all'] > 0])} 筆")
    print(f"  推文數 = 0 的文章: {len(final_data[final_data['pushes_all'] == 0])} 筆")
    
    # 過濾掉標題為空的文章（錯誤處理產生的占位數據）
    final_data = final_data[final_data['title'] != '']
    print(f"📋 過濾後數據: {len(final_data)} 筆（移除了 {len(dic['aid']) - len(final_data)} 筆錯誤數據）")

    print(f'頁面處理完成 - 成功: {success_count} 筆，錯誤: {error_count} 筆')
    
    if target_date:
        print(f'📅 過舊文章: {old_articles_count} 篇（早於 {target_date.strftime("%Y-%m-%d")}）')

    return final_data, should_stop


@app.task(bind=True)
def crawl_ptt_page_task(self, board_name=None, page_index=None, target_days=None):
    """Celery 任務：爬取 PTT 指定頁面"""
    # 初始化資料庫
    if not init_database():
        return {'status': 'error', 'message': '資料庫初始化失敗'}
    
    if board_name is None:
        board_name = PTT_BOARD
    
    if page_index is None:
        # 自動偵測最新頁面
        try:
            index_url = f'https://www.ptt.cc/bbs/{board_name}/index.html'
            index_page = ArticleListPage(index_url)
            previous_url = index_page.previous.url
            page_index = int(previous_url[previous_url.find('index')+5:previous_url.find('.html')]) + 1
            print(f'自動偵測起始頁面: {page_index}')
        except Exception as e:
            print(f'無法取得起始頁面，使用預設值: {e}')
            page_index = 1

    # 計算目標日期
    target_date = None
    if target_days:
        target_date = datetime.datetime.now() - datetime.timedelta(days=target_days)
        print(f'📅 目標日期：{target_date.strftime("%Y年%m月%d日")} 之後的文章')

    try:
        print(f"開始爬取 {board_name} 版第 {page_index} 頁")
        
        # 爬取單一頁面
        df, should_stop = ptt_crawl_single_page(board_name, page_index, target_date)
        
        if not df.empty:
            # 上傳到資料庫
            uploaded_count = upload_ptt_data_to_mysql(df)
            
            result = {
                'status': 'success',
                'board': board_name,
                'page': page_index,
                'articles_found': len(df),
                'articles_uploaded': uploaded_count,
                'should_stop': should_stop
            }
            
            print(f"✅ 任務完成：{board_name} 第 {page_index} 頁，找到 {len(df)} 篇文章，上傳 {uploaded_count} 筆")
            return result
            
        else:
            print(f"⚠️  第 {page_index} 頁無有效資料")
            return {
                'status': 'no_data',
                'board': board_name,
                'page': page_index,
                'articles_found': 0,
                'articles_uploaded': 0,
                'should_stop': should_stop
            }
            
    except Exception as e:
        print(f"❌ 爬取任務失敗：{str(e)}")
        return {
            'status': 'error',
            'board': board_name,
            'page': page_index,
            'error': str(e)
        }


@app.task(bind=True)
def crawl_ptt_recent_pages_task(self, board_name=None, target_days=7, max_pages=None):
    """Celery 任務：爬取 PTT 近期文章（多頁）"""
    # 初始化資料庫
    if not init_database():
        return {'status': 'error', 'message': '資料庫初始化失敗'}
    
    if board_name is None:
        board_name = PTT_BOARD
    
    if max_pages is None:
        print(f"🌟 開始爬取 {board_name} 版近 {target_days} 天的文章（無頁數限制，直到找到所有指定天數內的文章）")
    else:
        print(f"🌟 開始爬取 {board_name} 版近 {target_days} 天的文章（最多 {max_pages} 頁）")
    
    # 計算目標日期
    target_date = datetime.datetime.now() - datetime.timedelta(days=target_days)
    print(f'📅 目標日期：{target_date.strftime("%Y年%m月%d日")} 之後的文章')
    
    # 取得起始頁面
    try:
        index_url = f'https://www.ptt.cc/bbs/{board_name}/index.html'
        index_page = ArticleListPage(index_url)
        previous_url = index_page.previous.url
        start_page = int(previous_url[previous_url.find('index')+5:previous_url.find('.html')]) + 1
        print(f'自動偵測起始頁面: {start_page}')
    except Exception as e:
        print(f'無法取得起始頁面，使用預設值: {e}')
        start_page = 1
    
    total_articles = 0
    total_uploaded = 0
    pages_processed = 0
    
    try:
        page_count = 0
        while True:
            current_page = start_page - page_count
            
            if current_page <= 0:
                print('已到達最早頁面，爬取完成')
                break
            
            # 如果設定了最大頁數限制，檢查是否超過
            if max_pages is not None and page_count >= max_pages:
                print(f'已達到最大頁數限制 ({max_pages} 頁)，停止爬取')
                break
                
            print(f"\n--- 處理第 {page_count+1} 頁 (頁面編號: {current_page}) ---")
            
            # 爬取單一頁面
            df, should_stop = ptt_crawl_single_page(board_name, current_page, target_date)
            
            if not df.empty:
                # 上傳到資料庫
                uploaded_count = upload_ptt_data_to_mysql(df)
                total_articles += len(df)
                total_uploaded += uploaded_count
                print(f'第 {page_count+1} 頁完成，成功取得 {len(df)} 筆資料，上傳 {uploaded_count} 筆')
            else:
                print(f'第 {page_count+1} 頁無有效資料')
            
            pages_processed += 1
            page_count += 1
            
            # 如果發現過舊文章，停止爬取
            if should_stop:
                print(f'📅 發現過舊文章，停止爬取')
                break
        
        result = {
            'status': 'success',
            'board': board_name,
            'target_days': target_days,
            'pages_processed': pages_processed,
            'total_articles': total_articles,
            'total_uploaded': total_uploaded
        }
        
        print(f"✅ 批量爬取完成：{board_name} 版，處理 {pages_processed} 頁，找到 {total_articles} 篇文章，上傳 {total_uploaded} 筆")
        return result
        
    except Exception as e:
        print(f"❌ 批量爬取任務失敗：{str(e)}")
        return {
            'status': 'error',
            'board': board_name,
            'pages_processed': pages_processed,
            'total_articles': total_articles,
            'total_uploaded': total_uploaded,
            'error': str(e)
        }





def get_ptt_user_agent():
    """取得隨機 User-Agent"""
    try:
        from fake_useragent import UserAgent
        ua = UserAgent()
        return ua.random
    except:
        return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'


def simple_ptt_crawl(board_name, page_index, target_date=None):
    """簡化版 PTT 爬蟲，爬取單一頁面"""
    try:
        # 建構頁面 URL
        if page_index:
            url = f'https://www.ptt.cc/bbs/{board_name}/index{page_index}.html'
        else:
            url = f'https://www.ptt.cc/bbs/{board_name}/index.html'
        
        print(f"正在爬取: {url}")
        
        # 發送請求
        headers = {'User-Agent': get_ptt_user_agent()}
        response = requests.get(url, cookies={'over18': '1'}, headers=headers, timeout=PTT_TIMEOUT)
        
        if response.status_code != 200:
            print(f"頁面請求失敗: {response.status_code}")
            return pd.DataFrame(), False
        
        # 解析頁面
        soup = BeautifulSoup(response.text, 'html.parser')
        article_tags = soup.find_all('div', 'r-ent')
        
        # 存儲文章資料
        articles_data = []
        should_stop = False
        
        for tag in article_tags:
            try:
                # 取得標題和 URL
                title_tag = tag.find('div', class_='title')
                a_tag = title_tag.find('a') if title_tag else None
                
                if not a_tag:
                    continue  # 跳過已刪除的文章
                
                title = a_tag.get_text().strip()
                article_url = a_tag.get('href').strip()
                
                # 取得其他資訊
                score_tag = tag.find('div', class_='nrec')
                score = score_tag.get_text().strip() if score_tag else ''
                
                date_tag = tag.find('div', class_='date')
                date = date_tag.get_text().strip() if date_tag else ''
                
                author_tag = tag.find('div', class_='author')
                author = author_tag.get_text().strip() if author_tag else ''
                
                # 解析標題分類
                category, isreply, isforward = parse_title(title)
                
                # 建立文章資料
                article_data = {
                    'aid': article_url.split('/')[-1].replace('.html', '') if article_url else '',
                    'board': board_name,
                    'author': author,
                    'title': title,
                    'category': category,
                    'content': '',  # 簡化版不爬取內文
                    'date': date,
                    'ip': 'Unknown',  # 簡化版不爬取 IP
                    'pushes_all': 0,
                    'pushes_like': 0,
                    'pushes_boo': 0,
                    'pushes_neutral': 0,
                    'pushes_score': 0,
                    'url': article_url,
                }
                
                articles_data.append(article_data)
                
            except Exception as e:
                print(f"處理文章時發生錯誤: {e}")
                continue
        
        # 轉換為 DataFrame
        df = pd.DataFrame(articles_data)
        print(f"成功爬取 {len(df)} 篇文章摘要")
        
        return df, should_stop
        
    except Exception as e:
        print(f"爬取頁面時發生錯誤: {e}")
        return pd.DataFrame(), False


@app.task()
def crawl_ptt_page(board_name=None, page_index='', target_days=3):
    """爬取 PTT 版面指定頁面的文章摘要"""
    if not board_name:
        board_name = PTT_BOARD
    
    print(f"開始爬取 PTT {board_name} 版，頁面: {page_index if page_index else '最新'}")
    
    try:
        # 計算目標日期
        target_date = datetime.datetime.now() - datetime.timedelta(days=target_days)
        
        # 爬取頁面
        df, should_stop = simple_ptt_crawl(board_name, page_index, target_date)
        
        if not df.empty:
            # 上傳到 MySQL
            upload_ptt_data_to_mysql(df)
            print(f"PTT {board_name} 版第 {page_index} 頁資料已成功上傳到資料庫")
            return f"成功爬取並儲存 {len(df)} 篇文章"
        else:
            print(f"PTT {board_name} 版第 {page_index} 頁無有效資料")
            return "無有效資料"
            
    except Exception as e:
        error_msg = f"爬取 PTT {board_name} 版第 {page_index} 頁時發生錯誤: {e}"
        print(error_msg)
        return error_msg


@app.task()
def crawl_ptt_recent(board_name=None, max_pages=10, target_days=3):
    """爬取 PTT 版面近期多個頁面"""
    if not board_name:
        board_name = PTT_BOARD
    
    print(f"開始爬取 PTT {board_name} 版近 {target_days} 天的文章，最多 {max_pages} 頁")
    
    try:
        # 取得起始頁面編號
        index_url = f'https://www.ptt.cc/bbs/{board_name}/index.html'
        response = requests.get(index_url, cookies={'over18': '1'}, 
                              headers={'User-Agent': get_ptt_user_agent()}, timeout=PTT_TIMEOUT)
        
        if response.status_code != 200:
            return f"無法取得 {board_name} 版首頁"
        
        soup = BeautifulSoup(response.text, 'html.parser')
        prev_link = soup.find('a', string='‹ 上頁')
        if prev_link:
            prev_url = prev_link.get('href')
            start_index = int(prev_url.split('index')[1].split('.html')[0]) + 1
        else:
            start_index = 1
        
        total_articles = 0
        
        # 爬取多個頁面
        for page_offset in range(max_pages):
            page_index = start_index - page_offset
            if page_index <= 0:
                break
            
            print(f"爬取第 {page_offset + 1}/{max_pages} 頁 (index: {page_index})")
            
            df, should_stop = simple_ptt_crawl(board_name, page_index)
            
            if not df.empty:
                upload_ptt_data_to_mysql(df)
                total_articles += len(df)
                print(f"第 {page_offset + 1} 頁完成，累計 {total_articles} 篇文章")
            
            # 加入延遲
            delay = random.uniform(PTT_DELAY_MIN, PTT_DELAY_MAX)
            time.sleep(delay)
        
        return f"成功爬取並儲存 {total_articles} 篇文章"
        
    except Exception as e:
        error_msg = f"爬取 PTT {board_name} 版近期頁面時發生錯誤: {e}"
        print(error_msg)
        return error_msg


@app.task
def crawl_single_article_task(article_url):
    """
    單篇文章爬蟲任務
    接收文章網址，爬取該文章內容並存入資料庫
    類似 crawler_demo 中的 crawler_finmind_duplicate 任務
    """
    print(f"🔗 開始爬取單篇文章: {article_url}")
    
    try:
        # 檢查 URL 格式
        if not article_url or not article_url.startswith('https://www.ptt.cc/bbs/'):
            print(f"❌ 無效的文章網址: {article_url}")
            return {"status": "error", "message": "無效的文章網址"}
        
        # 爬取文章內容
        article_data = crawl_single_article(article_url)
        
        if not article_data:
            print(f"⚠️ 無法爬取文章內容: {article_url}")
            return {"status": "warning", "message": "無法爬取文章內容"}
        
        # 儲存到資料庫
        df = pd.DataFrame([article_data])
        save_count = upload_ptt_data_to_mysql(df)
        
        print(f"✅ 文章爬取完成: {article_data.get('title', 'unknown')[:30]}...")
        print(f"💾 資料庫儲存: {save_count} 筆")
        
        return {
            "status": "success",
            "article_url": article_url,
            "article_title": article_data.get('title', ''),
            "save_count": save_count,
            "message": "文章爬取與儲存成功"
        }
        
    except Exception as e:
        error_msg = f"爬取文章失敗: {str(e)}"
        print(f"❌ {error_msg}")
        
        return {
            "status": "error",
            "article_url": article_url,
            "error": error_msg
        }


def crawl_single_article(article_url):
    """
    爬取單篇 PTT 文章的詳細內容
    """
    try:
        ua = UserAgent()
        headers = {'User-Agent': ua.random}
        
        response = requests.get(article_url, cookies={'over18': '1'}, 
                              headers=headers, timeout=PTT_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 取得文章基本資訊
        main_content = soup.find('div', id='main-content')
        if not main_content:
            print(f"⚠️ 找不到文章內容: {article_url}")
            return None
        
        # 解析 meta 資訊
        metas = main_content.find_all('div', class_='article-metaline')
        author = ""
        title = ""
        date = ""
        
        try:
            if len(metas) >= 3:
                author = metas[0].find('span', class_='article-meta-value').get_text().strip()
                title = metas[1].find('span', class_='article-meta-value').get_text().strip()
                date = metas[2].find('span', class_='article-meta-value').get_text().strip()
        except:
            # 使用備用方法
            title_element = soup.find('meta', property='og:title')
            title = title_element['content'] if title_element else "無標題"
        
        # 解析標題分類
        category, isreply, isforward = parse_title(title)
        
        # 取得文章 ID
        aid = article_url.split('/')[-1].replace('.html', '') if article_url else ''
        
        # 取得版面名稱
        board = extract_board_from_url(article_url)
        
        # 移除 meta 標籤並取得內文
        content_copy = main_content.__copy__()
        for meta in content_copy.find_all('div', class_='article-metaline'):
            meta.extract()
        for meta in content_copy.find_all('div', class_='article-metaline-right'):
            meta.extract()
        
        # 移除推文
        for push in content_copy.find_all('div', class_='push'):
            push.extract()
            
        content = content_copy.get_text().strip()
        
        # 取得 IP
        ip = ""
        try:
            ip_tag = soup.find('span', class_='f2')
            if ip_tag:
                ip_text = ip_tag.get_text()
                import re
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', ip_text)
                if ip_match:
                    ip = ip_match.group(1)
        except:
            pass
        
        # 解析推文
        push_tags = soup.find_all('div', class_='push')
        pushes_all = len(push_tags)
        pushes_like = 0
        pushes_boo = 0
        pushes_neutral = 0
        
        for push_tag in push_tags:
            try:
                push_type = push_tag.find('span', class_='push-tag').get_text().strip()
                if '推' in push_type:
                    pushes_like += 1
                elif '噓' in push_type:
                    pushes_boo += 1
                else:
                    pushes_neutral += 1
            except:
                pushes_neutral += 1
        
        pushes_score = pushes_like - pushes_boo
        
        # 建立文章資料 (符合資料庫結構)
        article_data = {
            'aid': aid,
            'board': board,
            'author': author,
            'title': title,
            'category': category,
            'content': content,
            'date': date,
            'ip': ip,
            'pushes_all': pushes_all,
            'pushes_like': pushes_like,
            'pushes_boo': pushes_boo,
            'pushes_neutral': pushes_neutral,
            'pushes_score': pushes_score,
            'url': article_url
        }
        
        return article_data
        
    except Exception as e:
        print(f"❌ 爬取文章失敗 {article_url}: {e}")
        return None


def extract_board_from_url(url):
    """從文章網址中提取版面名稱"""
    try:
        # URL 格式: https://www.ptt.cc/bbs/Drink/M.1234567890.A.html
        parts = url.split('/')
        if len(parts) >= 5:
            return parts[4]  # 取得版面名稱
    except:
        pass
    return "unknown"
