"""
PTT 爬蟲任務發送器 - 分散式架構
發送任務到 Celery 佇列，採用分散式處理模式
"""
import datetime
import time
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent


def send_distributed_crawl_task(board_name='Drink', target_days=30, max_pages=None):
    """
    發送分散式 PTT 爬蟲任務
    採用「Producer 分析頁面，直接分發文章任務給 Worker 並行爬取」的流程

    Args:
        board_name: 版面名稱 (如 'Drink')
        target_days: 爬取最近幾天的文章
        max_pages: 最多處理幾頁 (None = 無限制)

    分散式處理流程:
    1. Worker 啟動時自動完成資料表初始化（避免多程序競爭）
    2. Producer 逐頁分析版面，收集所有符合條件的文章URL
    3. Producer 將文章任務分發給 Worker 池並行處理
    4. Worker 處理單篇文章爬取與資料庫儲存
    """
    from crawler.tasks_ptt_crawler import crawl_single_article_task
    import random

    print(f"🚀 開始分散式 PTT 爬蟲任務")
    print(f"📍 目標版面：{board_name}")
    print(f"📅 爬取範圍：最近 {target_days} 天的文章")
    print(f"📄 最大頁數：{max_pages if max_pages else '無限制'}")

    # 移除 Producer 端初始化：Worker 自動處理資料表初始化
    print(f"🛠️ 資料表初始化已交由 Worker 自動處理")

    target_date = datetime.datetime.now() - datetime.timedelta(days=target_days)
    print(f"📅 目標日期：{target_date.strftime('%Y年%m月%d日')} 之後的文章")

    total_articles_collected = 0
    total_tasks_sent = 0
    all_article_urls = []  # 收集所有文章URL

    try:
        # 第一階段：Producer 自己分析頁面，收集所有文章URL
        print(f"\n🔍 第一階段：分析頁面並收集文章URL")
        print(f"🌐 正在取得 {board_name} 版的起始頁面...")
        
        base_url = f"https://www.ptt.cc/bbs/{board_name}/index.html"
        ua = UserAgent()
        headers = {'User-Agent': ua.random}

        response = requests.get(base_url, cookies={'over18': '1'},
                                headers=headers, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # 找到上一頁的連結來推算當前頁碼
        prev_link = soup.find('a', string='‹ 上頁')
        if prev_link and prev_link.get('href'):
            import re
            match = re.search(r'index(\d+)\.html', prev_link['href'])
            if match:
                current_page = int(match.group(1)) + 1
            else:
                current_page = 1
        else:
            current_page = 1

        print(f"📄 找到最新頁面編號: {current_page}")

        # 逐頁分析，收集文章URL
        pages_processed = 0
        max_pages_to_check = max_pages if max_pages else 50
        
        for page_offset in range(max_pages_to_check):
            current_page_num = current_page - page_offset
            if current_page_num <= 0:
                break

            page_url = f"https://www.ptt.cc/bbs/{board_name}/index{current_page_num}.html"
            print(f"\n--- � 分析第 {current_page_num} 頁 ---")
            
            # Producer 自己分析頁面
            page_articles = analyze_page_for_articles(page_url, target_days, current_page_num)
            
            if page_articles is None:  # 發生錯誤
                continue
                
            if page_articles['should_stop']:
                print(f"🛑 第 {current_page_num} 頁發現過舊文章，停止分析")
                break
                
            # 收集這一頁的文章URL
            page_article_urls = page_articles['article_urls']
            all_article_urls.extend(page_article_urls)
            
            print(f"📊 第 {current_page_num} 頁結果:")
            print(f"   📰 總文章數: {page_articles['total_articles']}")
            print(f"   ✅ 符合條件: {len(page_article_urls)} 篇")
            print(f"   📌 跳過置頂: {page_articles['skipped_pinned']} 篇")
            print(f"   ⏰ 過舊文章: {page_articles['old_articles']} 篇")
            
            total_articles_collected += len(page_article_urls)
            pages_processed += 1
            
            # 短暫延遲
            time.sleep(random.uniform(1, 2))

        print(f"\n📊 頁面分析完成！")
        print(f"   � 分析頁面數: {pages_processed}")
        print(f"   📰 收集文章數: {len(all_article_urls)}")

        # 第二階段：分發所有文章任務
        print(f"\n� 第二階段：分發文章爬取任務")
        article_tasks = []
        
        for i, article_url in enumerate(all_article_urls, 1):
            print(f"📤 分發文章任務 {i}/{len(all_article_urls)}: {article_url.split('/')[-1]}")
            task = crawl_single_article_task.apply_async(
                args=[article_url],
                queue='ptt'
            )
            article_tasks.append({
                'task': task,
                'url': article_url,
                'task_id': task.id
            })
            total_tasks_sent += 1

        print(f"\n📋 已分發 {len(article_tasks)} 個文章爬取任務")

        # 第三階段：Fire-and-forget 模式，不等待任務結果
        print(f"\n🎯 第三階段：任務已分發，採用 fire-and-forget 模式")
        print(f"📋 分發的任務 ID 列表：")
        for task_info in article_tasks:
            print(f"   📝 {task_info['task_id'][:16]}... -> {task_info['url'].split('/')[-1]}")

        print(f"\n🎯 分散式爬蟲任務分發完成!")
        print(f"📊 最終統計:")
        print(f"   📄 分析頁面數: {pages_processed}")
        print(f"   📰 收集文章數: {len(all_article_urls)}")
        print(f"   🔗 分發任務數: {total_tasks_sent}")
        print(f"   🚀 任務模式: Fire-and-forget (不等待結果)")
        print(f"\n💡 監控方式:")
        print(f"   🌸 Flower 監控介面: http://localhost:5555")
        print(f"   📋 Worker 日誌: make logs")
        print(f"   🗄️ phpMyAdmin 資料庫: http://localhost:8000")
        print(f"\n⚠️  注意：Worker 會在背景處理這些任務，請透過上述監控方式查看進度。")

        return {
            'status': 'success',
            'pages_processed': pages_processed,
            'articles_collected': len(all_article_urls),
            'tasks_sent': total_tasks_sent,
            'mode': 'fire-and-forget'
        }

    except Exception as e:
        print(f"❌ 分散式爬蟲任務發送失敗: {e}")
        return {'status': 'error', 'message': str(e)}


def analyze_page_for_articles(page_url, target_days, page_number):
    """
    Producer 自己分析頁面，收集文章URL
    
    Args:
        page_url: 頁面網址
        target_days: 目標天數
        page_number: 頁面編號
        
    Returns:
        dict: 包含文章URL列表和統計資訊
    """
    import random
    from crawler.config import PTT_DELAY_MIN, PTT_DELAY_MAX, PTT_TIMEOUT
    
    try:
        ua = UserAgent()
        headers = {'User-Agent': ua.random}
        
        time.sleep(random.uniform(PTT_DELAY_MIN, PTT_DELAY_MAX))
        response = requests.get(page_url, cookies={'over18': '1'},
                               headers=headers, timeout=PTT_TIMEOUT)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 使用 CSS 選擇器取得所有文章
        all_articles = soup.select('div.r-ent')
        if not all_articles:
            print("❌ 找不到任何文章")
            return None
            
        # 只有第一頁（最新頁面）需要檢查分隔線
        articles_to_process = []
        skipped_pinned = 0
        
        # 判斷是否為第一頁（通過檢查是否有分隔線）
        separator = soup.select_one('div.r-list-sep')
        
        if separator:
            # 第一頁：只處理分隔線之前的文章
            print(f"📌 第一頁：發現分隔線，將排除置頂文章")
            list_container = soup.select_one('div.r-list-container')
            if list_container:
                all_elements = list_container.select('div.r-ent, div.r-list-sep')
                for element in all_elements:
                    if 'r-list-sep' in element.get('class', []):
                        # 遇到分隔線，停止收集文章
                        print(f"📌 分隔線前共收集 {len(articles_to_process)} 篇文章")
                        break
                    elif 'r-ent' in element.get('class', []):
                        articles_to_process.append(element)
                skipped_pinned = len(all_articles) - len(articles_to_process)
            else:
                articles_to_process = all_articles
        else:
            # 非第一頁：處理所有文章
            print(f"📄 非第一頁：處理所有文章")
            articles_to_process = all_articles
            
        # 分析文章，收集URL
        article_urls = []
        old_articles_count = 0
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=target_days)
        
        for article in articles_to_process:
            try:
                # 取得文章連結
                title_div = article.find('div', class_='title')
                if not title_div:
                    continue
                    
                link_element = title_div.find('a')
                if not link_element:
                    continue  # 跳過已刪除文章
                    
                article_url = 'https://www.ptt.cc' + link_element['href']
                article_title = link_element.get_text().strip()
                
                # 取得文章日期
                date_div = article.find('div', class_='date')
                if not date_div:
                    continue
                    
                date_str = date_div.get_text().strip()
                
                # 解析日期 (格式: "12/29")
                try:
                    month, day = map(int, date_str.split('/'))
                    current_year = datetime.datetime.now().year
                    article_date = datetime.datetime(current_year, month, day)
                    
                    # 如果文章日期在未來，表示是去年的文章
                    if article_date > datetime.datetime.now():
                        article_date = article_date.replace(year=current_year - 1)
                        
                except (ValueError, IndexError):
                    print(f"⚠️ 無法解析日期: {date_str}")
                    continue
                    
                # 檢查文章是否在目標時間範圍內
                if article_date < cutoff_date:
                    old_articles_count += 1
                    print(f"⏰ 發現過舊文章: {article_title[:30]}... ({date_str})")
                    continue
                    
                # 收集符合條件的文章URL
                article_urls.append(article_url)
                
            except Exception as e:
                print(f"⚠️ 處理文章時出錯: {e}")
                continue
                
        return {
            'article_urls': article_urls,
            'total_articles': len(all_articles),
            'skipped_pinned': skipped_pinned,
            'old_articles': old_articles_count,
            'should_stop': old_articles_count > 0  # 如果有過舊文章，建議停止
        }
        
    except Exception as e:
        print(f"❌ 分析頁面 {page_number} 時發生錯誤: {e}")
        return None


if __name__ == "__main__":
    print("🚀 PTT 分散式爬蟲任務發送器")
    print("=" * 60)
    print("採用分散式架構：逐頁分析，多 Worker 並行處理文章")
    print("=" * 60)

    print("\n🚀 開始執行分散式爬蟲...")
    # 執行分散式爬蟲任務
    result = send_distributed_crawl_task(
        board_name='Drink',
        target_days=30,    # 爬取近 30 天
        max_pages=5        # 測試用，最多處理5頁
    )

    if result['status'] == 'success':
        print("\n🎉 分散式爬蟲任務分發成功!")
    else:
        print(f"\n❌ 分散式爬蟲任務分發失敗: {result.get('message', '未知錯誤')}")
