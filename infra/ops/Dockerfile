# Backup jobs (F17, ADR-016): the app image plus sqlpackage, running app.ops.backup.
#   docker build -f infra/ops/Dockerfile --build-arg APP_IMAGE=<app image> -t cashflow-ops .
ARG APP_IMAGE
FROM ${APP_IMAGE}

USER root
# sqlpackage (self-contained .NET) needs ICU; the latest release from Microsoft.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl unzip libicu72 ca-certificates \
 && curl -fsSL https://aka.ms/sqlpackage-linux -o /tmp/sqlpackage.zip \
 && mkdir -p /opt/sqlpackage && unzip -q /tmp/sqlpackage.zip -d /opt/sqlpackage \
 && chmod +x /opt/sqlpackage/sqlpackage && rm /tmp/sqlpackage.zip \
 && apt-get purge -y curl unzip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/* \
 && /opt/sqlpackage/sqlpackage /version

ENV SQLPACKAGE=/opt/sqlpackage/sqlpackage
USER app
# Not the app's entrypoint (that runs migrations and the web server).
ENTRYPOINT ["python", "-m", "app.ops.backup"]
CMD ["export"]
