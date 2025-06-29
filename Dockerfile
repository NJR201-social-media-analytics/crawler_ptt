# 使用 Ubuntu 22.04 作為基礎映像檔（支援 Python 3.10）
# 明確指定 ARM64 架構，避免平台相容性問題
FROM --platform=linux/arm64 ubuntu:22.04

# 更新套件列表，並安裝 Python 3.10 以及 pip（Python 套件管理工具）
RUN apt-get update && \
    apt-get install python3.10 -y && \
    apt-get install python3-pip -y

# 安裝 uv（現代 Python 套件管理工具）
RUN pip install uv

# 建立工作目錄 /crawler
RUN mkdir /crawler

# 將當前目錄內容複製到容器的 /crawler 資料夾
COPY ./crawler /crawler/crawler
COPY ./pyproject.toml /crawler
COPY ./uv.lock /crawler
COPY ./README.md /crawler

# 設定容器的工作目錄為 /crawler，後續的指令都在這個目錄下執行
WORKDIR /crawler/

# 根據 uv.lock 安裝所有依賴（確保環境一致性）
RUN uv sync

# 設定語系環境變數，避免 Python 編碼問題
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8
