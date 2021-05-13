FROM python:3.8
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
EXPOSE 8383
COPY . ./
CMD ["uwsgi","--http","0.0.0.0:8383","--wsgi-file","forseeing.py","--callable","app","--processes","1","--threads","2","--stats","0.0.0.0:9192"]
