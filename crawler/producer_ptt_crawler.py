"""
PTT 爬蟲任務發送器
發送任務到 Celery 佇列
"""
from crawler.tasks_ptt_crawler import crawl_ptt_recent_pages_task

def send_recent_pages_task(board_name='Drink', target_days=7, max_pages=None):
    """發送近期頁面爬取任務"""
    print(f"🌟 發送 PTT 近期頁面爬取任務:")
    print(f"   版面: {board_name}")
    print(f"   目標天數: {target_days} 天")
    if max_pages is None:
        print(f"   頁數限制: 無限制（直到找到所有指定天數內的文章）")
    else:
        print(f"   最大頁數: {max_pages} 頁")
    
    # 發送任務到 ptt 佇列
    result = crawl_ptt_recent_pages_task.apply_async(
        args=[board_name, target_days, max_pages],
        queue='ptt'
    )
    
    print(f"✅ 任務已發送，任務 ID: {result.id}")
    return result

if __name__ == "__main__":
    # 發送 PTT Drink 版近期爬取任務
    result = send_recent_pages_task(
        board_name='Drink',
        target_days=30,    # 爬取近 30 天
        max_pages=None     # 無頁數限制
    )
    
    print("🎯 PTT 爬蟲任務發送完成！")
    print("📊 請到 Flower 監控介面查看任務狀態: http://localhost:5555")
    print("🗄️ 請到 phpMyAdmin 查看資料: http://localhost:8000")
