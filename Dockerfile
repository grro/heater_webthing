FROM python:3-alpine

ENV port 8348
ENV addr http://example.org
ENV directory /etc/heater

RUN cd /etc
RUN mkdir app
WORKDIR /etc/app
ADD *.py /etc/app/
ADD requirements.txt /etc/app/.
RUN pip install -r requirements.txt

CMD python /etc/app/heater_webthing.py $port $addr $directory


