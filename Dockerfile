FROM python:3.8-slim
COPY . /app
WORKDIR /app
EXPOSE 8000
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
ENTRYPOINT ["python"]
CMD ["forseeing.py"]
