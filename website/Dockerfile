FROM python:3
ADD . /
RUN pip install --upgrade -r requirements.txt
EXPOSE 5000
CMD [ "gunicorn", "--workers", "4", "-k", "gevent", "--timeout", "120", "--bind", "0.0.0.0:5000", "app:app" ]
