FROM python:3.8-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
EXPOSE 8383
COPY . ./
ENTRYPOINT ["python"]
CMD ["forseeing.py"]
