"""
PTT 爬蟲核心模組

提供爬取 PTT 版面文章資料的核心功能
包含文章摘要解析、頁面爬取等功能
"""

import collections
import datetime
import json
import os
import random
import time
import urllib

import pandas as pd
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent
# 移除進度管理器導入，簡化為直接爬取


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
    """解析標準的 PTT URL

    Args:
        url (str): PTT 文章 URL

    Returns:
        tuple: (bbs_url, board_name, article_id)

    Example:
        >>> parse_std_url('https://www.ptt.cc/bbs/Gossiping/M.1512057611.A.16B.html')
        ('https://www.ptt.cc/bbs', 'Gossiping', 'M.1512057611.A.16B')
    """
    prefix, _, basename = url.rpartition('/')
    basename, _, _ = basename.rpartition('.')
    bbs, _, board = prefix.rpartition('/')
    bbs = bbs[1:]
    return bbs, board, basename


def parse_title(title):
    """解析文章標題以獲取更多資訊

    Args:
        title (str): 文章標題

    Returns:
        tuple: (category, is_reply, is_forward)

    Example:
        >>> parse_title('[問題] 這個飲料好喝嗎？')
        ('問題', False, False)
        >>> parse_title('Re: [心得] 某飲料店評價')
        ('心得', True, False)
        >>> parse_title('普通標題沒有分類')
        ('無分類', False, False)
    """
    # 檢查是否為回覆或轉發文章
    isreply = 'Re:' in title
    isforward = 'Fw:' in title
    
    # 尋找第一個 [ 和對應的 ]
    start_bracket = title.find('[')
    if start_bracket == -1:
        # 沒有找到 [，設為無分類
        return '無分類', isreply, isforward
    
    end_bracket = title.find(']', start_bracket)
    if end_bracket == -1:
        # 有 [ 但沒有對應的 ]，設為無分類
        return '無分類', isreply, isforward
    
    # 提取第一個 [] 內的內容
    category = title[start_bracket + 1:end_bracket].strip()
    
    # 如果提取到的分類為空，設為無分類
    if not category:
        return '無分類', isreply, isforward
    
    return category, isreply, isforward


def parse_username(full_name):
    """解析用戶名稱以獲取其用戶帳號和暱稱

    Args:
        full_name (str): 用戶全名

    Returns:
        tuple: (user_account, nickname)

    Example:
        >>> parse_username('seabox (歐陽盒盒)')
        ('seabox', '歐陽盒盒')
    """
    name, nickname = full_name.split(' (')
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
        """從 URL 讀取文章並返回 ArticlePage
        如果文章已被刪除，則引發 ArtitcleIsRemoved 錯誤
        """
        if self.isremoved:
            raise ArtitcleIsRemoved(self.removeinfo)
        return ArticlePage(self.url)


class Page:
    """頁面的基礎類別
    通過 URL 獲取網頁的 HTML 內容
    所有子類別的物件都應該先調用它的 __init__ 方法
    """
    ptt_domain = 'https://www.ptt.cc'

    def __init__(self, url):
        if not url:
            raise NoGivenURLForPage

        self.url = url

        url = urllib.parse.urljoin(self.ptt_domain, self.url)
        
        # 使用 fake-useragent 和 1 秒超時
        try:
            from fake_useragent import UserAgent
            ua = UserAgent()
            user_agent = ua.random
        except:
            # 如果 fake-useragent 無法使用，使用預設的 User-Agent
            user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        
        resp = requests.get(
            url=url, 
            cookies={'over18': '1'}, 
            verify=True, 
            timeout=1,
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
        soup = BeautifulSoup(self.html, 'lxml')
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
            _, self.board, basename = parse_std_url(
                self.related_urls['previous'])
            _, _, idx = basename.partition('index')
            self.idx = int(idx)+1

    @classmethod
    def from_board(cls, board, index=''):
        """從給定的版名和索引建立 ArticleListPage 物件的類別方法
        如果未給定索引，則建立並返回該版的最新 ArticleListPage
        """
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

    default_attrs = ['board', 'aid', 'author', 'date', 'content', 'ip']
    default_csv_attrs = default_attrs + ['pushes.count.score']
    default_json_attrs = default_attrs + \
        ['pushes.count', 'pushes.simple_expression']

    def __init__(self, url):
        super().__init__(url)

        _, _, self.aid = parse_std_url(url)

        # 設定文章標籤
        soup = BeautifulSoup(self.html, 'lxml')
        main_tag = soup.find('div', id='main-content')
        meta_value_tags = main_tag.find_all(
            'span', class_='article-meta-value')

        # 處理元資料
        try:
            self.author = meta_value_tags[0].get_text().strip()
            self.board = meta_value_tags[1].get_text().strip()
            self.title = meta_value_tags[2].get_text().strip()
            self.date = meta_value_tags[3].get_text().strip()

            self.category, self.isreply, self.isforward = parse_title(
                self.title)
            self.datetime = datetime.datetime.strptime(
                self.date, '%a %b %d %H:%M:%S %Y')
        except:
            self.author, self.board, self.title, self.date = '', '', '', ''
            self.category, self.isreply, self.isforward = '', False, False
            self.datetime = None

        # 移除元資料標籤
        for tag in main_tag.select('div.article-metaline'):
            tag.extract()
        for tag in main_tag.select('div.article-metaline-right'):
            tag.extract()

        # 獲取推文並移除推文標籤
        self.pushes = Pushes(self)
        push_tags = main_tag.find_all('div', class_='push')
        for tag in push_tags:
            tag.extract()
        for tag in push_tags:
            if not tag.find('span', 'push-tag'):
                continue
            push_type = tag.find(
                'span', class_='push-tag').string.strip(' \t\n\r')
            push_user = tag.find(
                'span', class_='push-userid').string.strip(' \t\n\r')
            push_content = tag.find('span', class_='push-content').strings
            push_content = ' '.join(push_content)[1:].strip(' \t\n\r')
            push_ipdatetime = tag.find(
                'span', class_='push-ipdatetime').string.strip(' \t\n\r')
            msg = Msg(type=push_type, user=push_user,
                      content=push_content, ipdatetime=push_ipdatetime)
            self.pushes.addmsg(msg)
        self.pushes.countit()

        # 處理特殊項目
        ip_tags = main_tag.find_all('span', class_='f2')
        dic = {}
        for tag in ip_tags:
            if '※' in tag.get_text():
                key, _, value = tag.get_text().partition(':')
                key = key.strip('※').strip()
                value = value.strip()
                if '引述' in key:
                    continue
                else:
                    dic.setdefault(key, []).append(value)
                    tag.extract()
        
        # 安全地提取 IP 資訊
        try:
            if '發信站' in dic and dic['發信站']:
                self.ip = dic['發信站'][0].split()[-1]
            else:
                # 嘗試其他可能的格式
                self.ip = self._extract_ip_fallback(main_tag)
        except (IndexError, AttributeError) as e:
            print(f"⚠️  無法提取 IP 資訊: {e}")
            self.ip = 'Unknown'

        # 移除 richcontent 標籤
        for tag in main_tag.find_all('div', class_='richcontent'):
            tag.extract()

        # 處理轉錄資訊
        trans = []
        for tag in main_tag.find_all('span', class_='f2'):
            if '轉錄至看板' in tag.get_text():
                trans.append(tag.previous_element.parent)
                trans.append(tag.get_text())
                trans.append(tag.next_sibling)
                tag.previous_element.parent.extract()
                tag.next_sibling.extract()
                tag.extract()

        # 分割主要內容和簽名檔
        try:
            main_content_str = str(main_tag)
            if '--' in main_content_str:
                parts = main_content_str.split('--')
                self.content = parts[0].strip()
                self.signature = parts[1] if len(parts) > 1 else ''
            else:
                # 如果沒有簽名檔分隔符號，將整個內容視為正文
                self.content = main_content_str.strip()
                self.signature = ''
        except Exception as e:
            print(f"⚠️  內容分割錯誤: {e}")
            self.content = str(main_tag).strip()
            self.signature = ''

        # 清理內容格式
        try:
            contents = self.content.split('\n')
            self.content = '\n'.join(content for content in contents if not (
                '<div' in content and 'main-content' in content))

            if self.signature:
                contents = self.signature.split('\n')
                self.signature = '\n'.join(
                    content for content in contents if not ('</div' in content))
        except Exception as e:
            print(f"⚠️  內容清理錯誤: {e}")
            # 保持原始內容

    @classmethod
    def from_board_aid(cls, board, aid):
        url = '/'.join(['/bbs', board, aid+'.html'])
        return cls(url)

    def __repr__(self):
        return 'ArticlePage("{}")'.format(self.url)

    def __str__(self):
        return self.title

    @classmethod
    def _recur_getattr(cls, obj, attr):
        if not '.' in attr:
            try:
                return getattr(obj, attr)
            except:
                return obj[attr]
        attr1, _, attr2 = attr.partition('.')
        obj = cls._recur_getattr(obj, attr1)
        return cls._recur_getattr(obj, attr2)

    def dump_json(self, *attrs, flat=True):
        """根據指定的屬性轉存文章為 JSON 字串"""
        data = {}
        if not attrs:
            attrs = self.default_json_attrs
        for attr in attrs:
            data[attr] = self._recur_getattr(self, attr)
        if flat:
            return json.dumps(data, ensure_ascii=False)
        else:
            return json.dumps(data, indent=4, ensure_ascii=False)

    def dump_csv(self, *attrs, delimiter=','):
        """根據指定的屬性轉存文章為 CSV 字串"""
        cols = []
        if not attrs:
            attrs = self.default_csv_attrs
        for attr in attrs:
            cols.append(self._recur_getattr(self, attr))
        cols = [repr(col) if '\n' in str(col) else str(col) for col in cols]
        return delimiter.join(cols)

    def _extract_ip_fallback(self, main_tag):
        """備用的 IP 提取方法"""
        try:
            # 方法1: 尋找包含 IP 格式的文字
            text_content = main_tag.get_text()
            import re
            ip_pattern = r'\((\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\)'
            ip_match = re.search(ip_pattern, text_content)
            if ip_match:
                return ip_match.group(1)
            
            # 方法2: 尋找其他可能的來源標記
            for tag in main_tag.find_all('span', class_='f2'):
                text = tag.get_text()
                if '來自:' in text or 'From:' in text:
                    ip_match = re.search(ip_pattern, text)
                    if ip_match:
                        return ip_match.group(1)
            
            # 方法3: 如果都找不到，返回預設值
            return 'Unknown'
            
        except Exception as e:
            print(f"⚠️  IP 備用提取方法失敗: {e}")
            return 'Unknown'


class Pushes:
    """用於模型化文章所有推文的類別"""

    def __init__(self, article):
        self.article = article
        self.msgs = []
        self.count = 0

    def __repr__(self):
        return 'Pushes({})'.format(repr(self.article))

    def __str__(self):
        return 'Pushes of Article {}'.format(self.Article)

    def addmsg(self, msg):
        self.msgs.append(msg)

    def countit(self):
        count_types = 'all abs like boo neutral'.split()
        self.count = dict(zip(count_types, [0, 0, 0, 0, 0]))
        for msg in self.msgs:
            if msg.type == '推':
                self.count['like'] += 1
            elif msg.type == '噓':
                self.count['boo'] += 1
            else:
                self.count['neutral'] += 1

        self.count['all'] = self.count['like'] + \
            self.count['boo'] + self.count['neutral']
        self.count['score'] = self.count['like'] - self.count['boo']

    @property
    def simple_expression(self):
        msgs = []
        attrs = ['type', 'user', 'content', 'ipdatetime']
        for msg in self.msgs:
            msgs.append(dict(zip(attrs, list(msg))))
        return msgs


def ptt_crawl(Board_Name, start, page, target_date=None):
    """爬取單一頁面的文章資料

    Args:
        Board_Name (str): 版面名稱
        start (int): 起始頁面編號
        page (int): 頁面偏移量
        target_date (datetime): 目標日期，只爬取此日期之後的文章

    Returns:
        tuple: (pandas.DataFrame, bool) - (包含文章資訊的 DataFrame, 是否應該停止爬取)
    """
    Board = ArticleListPage.from_board

    # 建立錯誤記錄目錄
    error_dir = os.path.join('errors', Board_Name)
    os.makedirs(error_dir, exist_ok=True)

    error_count = 0
    success_count = 0

    try:
        # 抓該板首頁的文章
        latest_page = Board(Board_Name, start-page)
        print(f'正在處理 {Board_Name} 版第 {start-page} 頁')
    except Exception as e:
        error_filename = f"{error_dir}/page_error_{start-page}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        print(f'無法載入頁面 {start-page}，錯誤: {e}')

        # 嘗試儲存錯誤頁面的 HTML
        try:
            url = f'https://www.ptt.cc/bbs/{Board_Name}/index{start-page}.html'
            
            # 使用 fake-useragent
            try:
                from fake_useragent import UserAgent
                ua = UserAgent()
                user_agent = ua.random
            except:
                user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            
            resp = requests.get(
                url, 
                cookies={'over18': '1'}, 
                timeout=1,
                headers={'User-Agent': user_agent}
            )
            with open(error_filename, 'w', encoding='utf-8') as f:
                f.write(f"<!-- Error occurred while loading page: {e} -->\n")
                f.write(f"<!-- URL: {url} -->\n")
                f.write(f"<!-- Status Code: {resp.status_code} -->\n")
                f.write(resp.text)
            print(f'錯誤頁面已儲存: {error_filename}')
        except Exception as save_error:
            print(f'無法儲存錯誤頁面: {save_error}')

        return pd.DataFrame(), False

    # 抓取資料
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

    for summary in latest_page:  # 只要抓最新的頁面
        if summary.isremoved:
            continue

        print(f'正在抓資料中...{summary.title[:50]}...')
        time.sleep(1)  # 固定延遲 1 秒

        try:
            article = summary.read()
            
            # 如果有設定目標日期，檢查文章日期
            if target_date and article.datetime:
                if article.datetime < target_date:
                    old_articles_count += 1
                    print(f'📅 文章日期過舊：{article.datetime.strftime("%Y-%m-%d %H:%M")}，跳過')
                    # 如果連續發現多篇過舊文章，可能整頁都是舊文章
                    if old_articles_count >= 3:
                        print(f'📅 發現連續 {old_articles_count} 篇過舊文章，可能需要停止爬取')
                        should_stop = True
                    continue
                else:
                    # 重置計數器，因為找到了新文章
                    old_articles_count = 0
            
            # 將所有內容儲存在一個[]
            ptt_aid.append(article.aid)
            ptt_author.append(article.author)
            ptt_board.append(article.board)
            ptt_category.append(article.category)
            ptt_title.append(article.title)
            ptt_content.append(article.content)
            ptt_url.append(article.url)
            ptt_date.append(article.date)
            ptt_ip.append(article.ip)
            ptt_all.append(article.pushes.count['all'])
            ptt_boo.append(article.pushes.count['boo'])
            ptt_like.append(article.pushes.count['like'])
            ptt_neutral.append(article.pushes.count['neutral'])
            ptt_score.append(article.pushes.count['score'])
            ptt_comment.append(article.pushes.simple_expression)

            success_count += 1

        except Exception as e:
            error_count += 1
            article_url = summary.url if hasattr(
                summary, 'url') and summary.url else 'unknown'
            article_title = summary.title if hasattr(
                summary, 'title') and summary.title else 'unknown'

            print(f'處理文章時發生錯誤: {article_title[:30]}... - {str(e)[:100]}')

            # 儲存錯誤文章的 HTML
            error_filename = f"{error_dir}/article_error_{summary.aid if hasattr(summary, 'aid') else 'unknown'}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

            try:
                if article_url and article_url != 'unknown':
                    full_url = f"https://www.ptt.cc{article_url}"
                    
                    # 使用 fake-useragent 和 1 秒超時
                    try:
                        from fake_useragent import UserAgent
                        ua = UserAgent()
                        user_agent = ua.random
                    except:
                        user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                    
                    resp = requests.get(
                        full_url, 
                        cookies={'over18': '1'}, 
                        timeout=1,
                        headers={'User-Agent': user_agent}
                    )

                    with open(error_filename, 'w', encoding='utf-8') as f:
                        f.write(
                            f"<!-- Error occurred while processing article -->\n")
                        f.write(f"<!-- Article Title: {article_title} -->\n")
                        f.write(f"<!-- Article URL: {full_url} -->\n")
                        f.write(f"<!-- Error Message: {str(e)} -->\n")
                        f.write(
                            f"<!-- Timestamp: {datetime.datetime.now().isoformat()} -->\n")
                        f.write(f"<!-- Status Code: {resp.status_code} -->\n")
                        f.write(resp.text)

                    print(f'錯誤文章已儲存: {error_filename}')

            except Exception as save_error:
                print(f'無法儲存錯誤文章: {save_error}')

            continue

    # 將結果做成df
    dic = {
        '文章編碼': ptt_aid,
        '作者': ptt_author,
        '版名': ptt_board,
        '分類': ptt_category,
        '標題': ptt_title,
        '內文': ptt_content,
        '日期': ptt_date,
        'IP位置': ptt_ip,
        '總留言數': ptt_all,
        '噓': ptt_boo,
        '推': ptt_like,
        '中立': ptt_neutral,
        '文章分數（正-負）': ptt_score,
        '所有留言': ptt_comment
    }
    final_data = pd.DataFrame(dic)
    # 去除空白的標題
    final_data = final_data[final_data['標題'] != '']

    print(f'頁面處理完成 - 成功: {success_count} 筆，錯誤: {error_count} 筆')
    
    if target_date:
        print(f'📅 過舊文章: {old_articles_count} 篇（早於 {target_date.strftime("%Y-%m-%d")}）')

    return final_data, should_stop


def crawl_ptt_page(Board_Name='Drink', start='', page_num=5, crawl_all=False, crawl_recent_days=False, target_days=3):
    """爬取 PTT 版面指定數量的頁面

    Args:
        Board_Name (str): 版面名稱，固定為 'Drink'
        start (str): 起始頁面編號，空字串代表從最新頁面開始
        page_num (int): 要爬取的頁面數量，預設為 5
        crawl_all (bool): 是否爬取所有頁面，預設為 False
        crawl_recent_days (bool): 是否按日期爬取近期頁面，預設為 False
        target_days (int): 爬取近幾天的文章，預設為 3

    Returns:
        pandas.DataFrame: 包含文章資訊的 DataFrame
    """
    if crawl_all:
        print(f'🌟 開始爬取 {Board_Name} 版的所有頁面')
    elif crawl_recent_days:
        print(f'🌟 開始爬取 {Board_Name} 版近 {target_days} 天的文章')
    else:
        print(f'🌟 開始爬取 {Board_Name} 版，共 {page_num} 頁')
    print('=' * 50)

    # 計算目標日期（近N天）
    if crawl_recent_days:
        target_date = datetime.datetime.now() - datetime.timedelta(days=target_days)
        print(f'📅 目標日期：{target_date.strftime("%Y年%m月%d日")} 之後的文章')

    t_start = time.time()  # 計時開始
    result_list = []
    total_success = 0
    total_errors = 0
    page_errors = 0
    articles_too_old = 0

    # 建立主要錯誤記錄目錄
    error_dir = os.path.join('errors', Board_Name)
    os.makedirs(error_dir, exist_ok=True)

    # 決定起始頁面
    if start.isdigit():
        start = int(start)
    else:
        try:
            index_url = f'https://www.ptt.cc/bbs/{Board_Name}/index.html'
            index_page = ArticleListPage(index_url)
            previous_url = index_page.previous.url
            start = int(previous_url[previous_url.find(
                'index')+5:previous_url.find('.html')]) + 1
            print(f'自動偵測起始頁面: {start}')
        except Exception as e:
            print(f'無法取得起始頁面，使用預設值: {e}')
            start = 1

    # 爬取頁面
    current_page = start
    pages_crawled = 0

    # 如果是爬取所有頁面，設定一個較大的上限
    if crawl_all:
        max_pages = start  # 從最新頁面爬到第1頁
        print(f'📊 預估最多爬取約 {max_pages} 頁')
    elif crawl_recent_days:
        max_pages = 200  # 設定一個合理的上限，避免無限循環
        print(f'📊 最多爬取 {max_pages} 頁（直到找到 {target_days} 天前的文章）')
    else:
        max_pages = page_num

    try:
        while pages_crawled < max_pages:
            try:
                page_index = start - pages_crawled
                
                # 如果爬取所有頁面，檢查是否已到達最早頁面
                if crawl_all and page_index <= 0:
                    print('已到達最早頁面，爬取完成')
                    break
                
                if crawl_all:
                    print(f'\n--- 處理第 {pages_crawled+1} 頁 (頁面編號: {page_index}) ---')
                elif crawl_recent_days:
                    print(f'\n--- 處理第 {pages_crawled+1} 頁 (頁面編號: {page_index}) - 尋找近 {target_days} 天文章 ---')
                else:
                    print(f'\n--- 處理第 {pages_crawled+1}/{page_num} 頁 (頁面編號: {page_index}) ---')

                # 傳遞目標日期給 ptt_crawl
                target_date_param = target_date if crawl_recent_days else None
                page_data, should_stop = ptt_crawl(Board_Name=Board_Name,
                                      start=start, page=pages_crawled, target_date=target_date_param)

                if not page_data.empty:
                    result_list.append(page_data)
                    page_success = len(page_data)
                    total_success += page_success
                    print(f'第 {pages_crawled+1} 頁完成，成功取得 {page_success} 筆資料')
                else:
                    print(f'第 {pages_crawled+1} 頁無有效資料')
                    page_errors += 1

                # 如果是按日期爬取且發現過舊文章，考慮停止
                if crawl_recent_days and should_stop:
                    print(f'📅 發現過舊文章，停止爬取')
                    break

                pages_crawled += 1

                # 顯示進度
                if pages_crawled % 10 == 0:
                    print(f"📊 已完成 {pages_crawled} 頁")

                # 加入延遲避免過度請求
                delay_time = random.uniform(0.5, 1.5)
                time.sleep(delay_time)

            except KeyboardInterrupt:
                print(f'\n⚠️ 用戶中斷爬取 (Ctrl+C)')
                print(f"爬蟲已停止")
                break

            except Exception as e:
                page_errors += 1
                print(f'爬取第 {pages_crawled+1} 頁時發生錯誤: {e}')

                # 儲存頁面錯誤資訊
                error_log_file = os.path.join(error_dir, 'page_errors.log')
                with open(error_log_file, 'a', encoding='utf-8') as f:
                    f.write(
                        f"{datetime.datetime.now().isoformat()} - Page {pages_crawled+1} (index {page_index}): {str(e)}\n")

                pages_crawled += 1
                continue

    except Exception as critical_error:
        print(f'發生嚴重錯誤: {critical_error}')
        return pd.DataFrame()

    # 檢查是否有資料
    if not result_list:
        print('\n❌ 沒有成功爬取到任何資料')
        return pd.DataFrame()

    print(f'\n--- 資料合併處理 ---')

    # 合併所有資料
    final_data = pd.concat(result_list, ignore_index=True)
    
    # 移除重複資料 (使用正確的中文欄位名稱)
    initial_count = len(final_data)
    final_data = final_data.drop_duplicates(subset=['標題', '作者'], keep='first')
    final_count = len(final_data)
    duplicate_count = initial_count - final_count

    # 保存資料
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    main_filename = f'ptt_{Board_Name}_{timestamp}.csv'
    latest_filename = f'ptt_{Board_Name}_latest.csv'
    
    # 確保 data 目錄存在
    os.makedirs('data', exist_ok=True)
    
    main_path = os.path.join('data', main_filename)
    latest_path = os.path.join('data', latest_filename)
    
    final_data.to_csv(main_path, index=False, encoding='utf-8-sig')
    final_data.to_csv(latest_path, index=False, encoding='utf-8-sig')

    t_end = time.time()  # 計時結束
    elapsed_time = int(t_end - t_start)

    # 產生詳細報告
    print(f'\n{"="*50}')
    print(f'🎉 爬取任務完成！')
    print(f'📊 統計報告:')
    print(f'   └─ 版面: {Board_Name}')
    if crawl_recent_days:
        print(f'   └─ 爬取模式: 近 {target_days} 天文章')
    elif crawl_all:
        print(f'   └─ 爬取模式: 所有頁面')
    else:
        print(f'   └─ 爬取模式: 指定 {page_num} 頁')
    print(f'   └─ 處理頁面: {pages_crawled} 頁')
    print(f'   └─ 頁面錯誤: {page_errors} 頁')
    print(f'   └─ 成功文章: {total_success} 篇')
    print(f'   └─ 重複移除: {duplicate_count} 篇')
    print(f'   └─ 最終資料: {final_count} 篇')
    print(f'   └─ 執行時間: {elapsed_time} 秒')
    print(f'\n📁 檔案已儲存:')
    print(f'   └─ 主檔案: {main_path}')
    print(f'   └─ 最新檔案: {latest_path}')
    print(f'{"="*50}')

    return final_data
    print(f'   └─ 成功文章: {total_success} 筆')
    print(f'   └─ 重複移除: {duplicate_count} 筆')
    print(f'   └─ 最終資料: {final_count} 筆')
    print(
        f'   └─ 花費時間: {elapsed_time} 秒 ({elapsed_time//60} 分 {elapsed_time % 60} 秒)')
    if crawl_all:
        print(f'   └─ 平均速度: {final_count/elapsed_time:.2f} 筆/秒')
    print(f'   └─ 主要檔案: {main_path}')
    print(f'   └─ 最新檔案: {latest_path}')

    if page_errors > 0:
        print(f'   └─ 錯誤記錄: {error_dir}/')

    print(f'{"="*50}')

    return final_data


def main():
    """自動執行 PTT Drink 版爬蟲 - 爬取近三天的頁面"""
    print('=== PTT Drink 版爬蟲工具 ===')
    print('自動開始爬取 Drink 版面 - 近三天的文章')
    
    board_name = 'Drink'  # 固定爬取 Drink 版
    start_input = ''       # 使用最新頁面
    crawl_recent_days = True  # 爬取近期頁面
    target_days = 3        # 爬取近三天

    print(f'設定：從最新頁面開始，爬取近 {target_days} 天的文章')
    print('⚠️  這會自動偵測文章日期並停止在三天前')
    print('開始執行...\n')

    # 執行爬蟲
    try:
        crawl_ptt_page(Board_Name=board_name, start=start_input, crawl_recent_days=crawl_recent_days, target_days=target_days)
    except KeyboardInterrupt:
        print('\n使用者中斷執行')
    except Exception as e:
        print(f'執行時發生錯誤: {e}')


if __name__ == '__main__':
    main()
