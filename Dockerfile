FROM fedora:43 AS base

ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN dnf5 -y upgrade \
    && dnf5 -y install \
        python3 \
        python3-pip \
        python3-devel \
        ca-certificates \
        curl \
        uv \
        @c-development \
        @development-tools \
        && dnf5 clean all

FROM base AS deps

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev

FROM base AS runtime

# copy installed deps + venv
COPY --from=deps /app /app

# copy source last
COPY . .

CMD ["uv", "run", "python", "-m", "hbot"]
