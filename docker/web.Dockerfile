FROM nginx:1.27-alpine

COPY docker/web_nginx.conf /etc/nginx/nginx.conf
COPY web_client /usr/share/nginx/html

