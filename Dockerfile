FROM caddy:2.8-alpine
COPY Caddyfile /etc/caddy/Caddyfile
# Only public site files; build scripts stay out of the image
COPY index.html tours.html multi-day-tours.html price-calculator.html destinations.html blog.html /srv/
COPY tours /srv/tours
COPY blog /srv/blog
COPY css /srv/css
COPY js /srv/js
COPY images /srv/images
COPY robots.txt* sitemap.xml* /srv/
