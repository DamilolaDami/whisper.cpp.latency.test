FROM debian:bookworm-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

ARG WHISPER_REF=master
RUN git clone --depth 1 --branch ${WHISPER_REF} https://github.com/ggerganov/whisper.cpp.git .

RUN cmake -B build \
        -DCMAKE_BUILD_TYPE=Release \
        -DWHISPER_BUILD_EXAMPLES=ON \
        -DBUILD_SHARED_LIBS=OFF \
    && cmake --build build --config Release -j"$(nproc)" --target whisper-server

ARG MODEL=small.en
RUN bash ./models/download-ggml-model.sh ${MODEL}


FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 ca-certificates ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

ARG MODEL=small.en
COPY --from=builder /build/build/bin/whisper-server /app/whisper-server
COPY --from=builder /build/models/ggml-${MODEL}.bin /app/models/ggml-${MODEL}.bin

COPY app.py /app/app.py
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV MODEL=small.en
ENV PORT=8080
ENV INTERNAL_PORT=8081
ENV THREADS=4
# Set API_KEY in Railway to enable bearer-token auth. Unset = open access.

EXPOSE 8080

CMD ["/app/entrypoint.sh"]
