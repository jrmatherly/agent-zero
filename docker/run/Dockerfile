# Use the pre-built base image for A0
# FROM apollos-ai-base:local
# FROM ghcr.io/jrmatherly/apollos-ai-base:testing
FROM ghcr.io/jrmatherly/apollos-ai-base:latest

# Check if the argument is provided, else throw an error
ARG BRANCH
RUN if [ -z "$BRANCH" ]; then echo "ERROR: BRANCH is not set!" >&2; exit 1; fi
ENV BRANCH=$BRANCH

# Copy filesystem files to root (installation scripts)
COPY ./fs/ /

# pre installation steps (apt-get update, SSH setup)
RUN bash /ins/pre_install.sh $BRANCH

# Clone repository and install Python packages + Playwright + preload.
# Done in a single layer so the pip/uv cache can be purged without bloating
# intermediate layers.  CACHE_DATE busts this layer on every release so the
# build always picks up the latest commit from the branch.
ARG CACHE_DATE=none
RUN echo "cache buster $CACHE_DATE" && \
    bash /ins/install_A0.sh $BRANCH && \
    . /ins/setup_venv.sh && \
    pip cache purge && \
    uv cache prune

# post installation steps (apt cleanup)
RUN bash /ins/post_install.sh $BRANCH

# Expose ports
EXPOSE 22 80 9000-9009

RUN chmod +x /exe/initialize.sh /exe/run_A0.sh /exe/run_searxng.sh /exe/run_tunnel_api.sh

# Grant appuser access to application and runtime directories (CD-C2)
RUN chown -R appuser:appuser /git/apollos-ai /opt/venv-a0 && \
    mkdir -p /a0 && chown appuser:appuser /a0

# initialize runtime and switch to supervisord
# NOTE: supervisord runs as root to manage sshd/cron; app processes run as
# appuser via user= directives in supervisord.conf
CMD ["sh", "-c", "exec /exe/initialize.sh $BRANCH"]
