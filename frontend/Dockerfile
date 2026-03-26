# ============================================================
# Frontend — простой Nginx с нашим HTML
# Тут мультистейдж не нужен (нет сборки), но если бы был React —
# первый стейдж был бы `npm run build`, второй — nginx
# ============================================================

FROM nginx:1.27-alpine

# Удаляем дефолтный конфиг
RUN rm /etc/nginx/conf.d/default.conf

# Копируем наш конфиг
COPY nginx.conf /etc/nginx/conf.d/pharmacy.conf

# Копируем статику
COPY index.html /usr/share/nginx/html/index.html

EXPOSE 80

# Nginx запускается от root, но worker processes — от nginx user (безопасно)
CMD ["nginx", "-g", "daemon off;"]
