# 使用 Ubuntu 22.04 作為基礎映像檔（支援 Python 3.10）
FROM ubuntu:22.04

# 更新套件列表，並安裝 Python 3.10 以及 pip（Python 套件管理工具）
RUN apt-get update && \
    apt-get install python3.10 -y && \
    apt-get install python3-pip -y && \
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1

# 安裝 uv（現代 Python 套件管理工具）
RUN pip install uv

# 建立工作目錄 /crawler
RUN mkdir /crawler

# 將當前目錄內容複製到容器的 /crawler 資料夾
COPY ./crawler /crawler/crawler
COPY ./pyproject.toml /crawler
COPY ./genenv.py /crawler
COPY ./uv.lock /crawler
COPY ./README.md /crawler
COPY ./local.ini /crawler

# 設定容器的工作目錄為 /crawler，後續的指令都在這個目錄下執行
WORKDIR /crawler/

# 根據 uv.lock 安裝所有依賴（確保環境一致性）
RUN uv sync

# 設定語系環境變數，避免 Python 編碼問題
ENV LC_ALL=C.UTF-8
ENV LANG=C.UTF-8

# 建立 .env 環境變數檔案（Docker 環境）
RUN ENV=DOCKER python3 genenv.py

# 啟動容器後，預設執行 bash（開啟終端）
CMD ["/bin/bash"]
