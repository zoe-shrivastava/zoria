# Build stage
FROM node:18-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./
COPY .npmrc* ./

# Install dependencies
# Use npm ci if package-lock.json exists (faster, more reliable)
# Otherwise use npm install (will create package-lock.json)
RUN if [ -f package-lock.json ]; then \
      npm ci; \
    else \
      npm install; \
    fi

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Verify build output (list contents to debug)
RUN echo "=== Build output ===" && \
    ls -la /app && \
    echo "=== Dist folder ===" && \
    ls -la /app/dist || (echo "ERROR: Build failed - dist folder not found" && exit 1) && \
    echo "=== Dist contents ===" && \
    find /app/dist -type f | head -20

# Production stage
FROM nginx:alpine

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Verify files are copied
RUN ls -la /usr/share/nginx/html || (echo "Files not copied" && exit 1)

# Copy nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
