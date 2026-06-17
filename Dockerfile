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


FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 ca-certificates ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG MODEL=small.en
COPY --from=builder /build/build/bin/whisper-server /app/whisper-server
COPY --from=builder /build/models/ggml-${MODEL}.bin /app/models/ggml-${MODEL}.bin

ENV MODEL=small.en
ENV PORT=8080
ENV THREADS=4

EXPOSE 8080

# Railway sets $PORT at runtime. THREADS should match the plan's vCPU count.
CMD ["/bin/sh", "-c", "exec /app/whisper-server \
    --host 0.0.0.0 \
    --port ${PORT} \
    --threads ${THREADS} \
    --model /app/models/ggml-${MODEL}.bin"]
