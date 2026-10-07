FROM postgres@sha256:0ea6700a3b4f0ae6ce746519073558aed4d88a79d8d07622a9a644946c7319c4
LABEL lightyear.tsql.purpose="public-fixture-coverage-preparation"
RUN apt-get update && apt-get install -y --no-install-recommends postgresql-16-plpgsql-check \
    && dpkg-query -W > /usr/local/share/lightyear-coverage-packages.txt
