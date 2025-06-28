"""
PTT Drink 版爬    print("📅 爬取範圍: 近30天的文章")

直接爬取 Drink 版面
"""

import datetime
import os
from ptt_crawler import crawl_ptt_page


def main():
    """主要執行函數 - 自動爬取 Drink 版近30天資料"""
    print("=== PTT Drink 版爬蟲程式 ===")
    print("🚀 啟動 PTT 爬蟲")
    print("🎯 固定爬取版面: Drink")
    print("� 爬取範圍: 近三天的文章")
    print("=" * 50)

    try:
        # 直接開始爬取近30天的資料
        data = crawl_ptt_page(Board_Name='Drink', crawl_recent_days=True, target_days=30)

        if not data.empty:
            current_count = len(data)
            print(f"\n🎉 爬取完成！成功取得 {current_count} 筆資料")
        else:
            print("\n⚠️  未取得任何資料")
            print("📝 請檢查:")
            print("   - 網路連線是否正常")
            print("   - errors/ 目錄中的錯誤記錄")

    except KeyboardInterrupt:
        print(f"\n⚠️ 用戶中斷程式 (Ctrl+C)")
        print("程式已停止")

    except Exception as e:
        print(f"❌ 爬取時發生錯誤：{e}")

        # 記錄主程式錯誤
        error_log_file = f'errors/main_errors_{datetime.datetime.now().strftime("%Y%m%d")}.log'
        os.makedirs('errors', exist_ok=True)
        with open(error_log_file, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.datetime.now().isoformat()} - Error: {str(e)}\n")

    print("=" * 50)


if __name__ == "__main__":
    main()
