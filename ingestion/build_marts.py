"""Build ``streamlit_app/data/analytics.duckdb`` from the raw CSVs (local only).

Raw CSVs -> staging (in-memory) -> ``marts`` tables, written to a
fresh DuckDB file containing only the ``marts`` schema the dashboard reads.

Run order: after ``ingest_kaggle.py`` and ``ingest_setlistfm.py``:

    uv run ingestion/build_marts.py

Honors ``DUCKDB_PATH`` (same override the dashboard uses). No credentials.
"""

# /// script
# requires-python = ">=3.13"
# dependencies = ["duckdb==1.5.4"]
# ///

import os
import sys
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parents[1]
MA_DIR = REPO_ROOT / "data" / "raw" / "metal_archives"
SFM_DIR = REPO_ROOT / "data" / "raw" / "setlistfm"
DEFAULT_OUT = REPO_ROOT / "streamlit_app" / "data" / "analytics.duckdb"

RAW_FILES = {
    "bands": MA_DIR / "metal_bands.csv",
    "albums": MA_DIR / "all_bands_discography.csv",
    "setlists": SFM_DIR / "setlists.csv",
    "songs": SFM_DIR / "songs.csv",
    "band_mapping": SFM_DIR / "band_mapping.csv",
}

# Inlined dbt macros -----------------------------------------------------------


def parse_subgenre(col: str) -> str:
    return (
        "trim(regexp_extract("
        f"regexp_extract({col}, '^([^(]+)', 1), '^([^/,]+)', 1))"
    )


# Staging models (in-memory ``staging`` schema) ---------------------------------

STAGING_SQL = {
    "stg_bands": rf"""
        with source as (
            select
                -- "Band ID" is unreliable; the URL's trailing number is the real id.
                regexp_extract("URL", '(\d+)$', 1) as band_id,
                "Name" as band_name,
                "Country" as country,
                "Genre" as genre,
                "Status" as status
            from read_csv($bands, header = true, all_varchar = true)
        ),
        deduped as (
            select *, row_number() over (partition by band_id order by band_name) as rn
            from source
        )
        select
            band_id,
            band_name,
            country,
            genre,
            {parse_subgenre("genre")} as primary_subgenre,
            status
        from deduped
        where rn = 1
    """,
    "stg_albums": r"""
        with source as (
            select
                "Band ID" as band_id,
                "Album Name" as album_name,
                "Type" as album_type,
                "Year" as year,
                "Reviews" as reviews
            from read_csv($albums, header = true, all_varchar = true)
        ),
        parsed as (
            select
                band_id,
                album_name,
                album_type,
                try_cast(year as bigint) as year,
                case
                    when reviews is null or reviews = 'No Reviews' then 0
                    else try_cast(nullif(regexp_extract(reviews, '^(\d+)', 1), '') as bigint)
                end as review_count,
                case
                    when reviews is null or reviews = 'No Reviews' then null
                    else try_cast(nullif(regexp_extract(reviews, '\((\d+)%\)', 1), '') as bigint)
                end as avg_review_pct
            from source
        ),
        deduped as (
            select
                *,
                row_number() over (
                    partition by band_id, album_name, year
                    order by review_count desc
                ) as rn
            from parsed
            where year is not null
        )
        select
            md5(band_id || '|' || album_name || '|' || cast(year as varchar)) as album_id,
            band_id,
            album_name,
            album_type,
            year,
            review_count,
            avg_review_pct
        from deduped
        where rn = 1
    """,
    # One row per band x genre keyword ("Progressive Death Metal" -> Progressive,
    # Death). Tags are word tokens of the genre string minus generic filler, so
    # keyword filters catch every compound genre that mentions the keyword —
    # unlike primary_subgenre, which keeps only the first phrase.
    "stg_band_genre_tags": r"""
        with tokens as (
            select
                band_id,
                trim(unnest(regexp_split_to_array(
                    regexp_replace(
                        replace(replace(coalesce(genre, ''),
                            'Hard Rock', 'Hard-Rock'),
                            'Middle Eastern', 'Middle-Eastern'),
                        '\([^)]*\)', ' ', 'g'
                    ),
                    '[/,;&+ ]+'
                )), '''’‘') as tok
            from staging.stg_bands
        )
        select distinct
            band_id,
            concat(upper(substr(tok, 1, 1)), substr(tok, 2)) as genre_tag
        from tokens
        where tok != ''
          and lower(tok) not in (
            'metal', 'rock', 'music', 'with', 'influences', 'elements',
            'and', 'or', 'of', 'various', 'n', 'roll',
            -- fragments of non-metal phrases ("Pop Rock", "New Age/Wave",
            -- "Dark Ambient", "Extreme Metal") that read as fake genres
            'pop', 'new', 'wave', 'age', 'dark', 'extreme'
          )
    """,
    "stg_band_mapping": """
        select
            cast(ma_band_id as varchar) as ma_band_id,
            ma_band_name,
            sfm_mbid,
            sfm_artist_name,
            match_type
        from read_csv($band_mapping, header = true)
    """,
    "stg_setlists": """
        with source as (
            select *
            from read_csv(
                $setlists,
                header = true,
                dateformat = '%d-%m-%Y',
                types = {
                    'setlist_id': 'VARCHAR',
                    'venue_id': 'VARCHAR',
                    'event_date': 'DATE',
                    'latitude': 'DOUBLE',
                    'longitude': 'DOUBLE'
                }
            )
        ),
        deduped as (
            select *, row_number() over (partition by setlist_id order by event_date) as rn
            from source
        )
        select
            setlist_id,
            artist_mbid,
            artist_name,
            event_date,
            extract(year from event_date) as event_year,
            extract(month from event_date) as event_month,
            venue_id,
            venue_name,
            city_name,
            state,
            country_code,
            country_name,
            latitude,
            longitude,
            tour_name
        from deduped
        where rn = 1
    """,
    "stg_songs": """
        with source as (
            select *
            from read_csv(
                $songs,
                header = true,
                types = {
                    'setlist_id': 'VARCHAR',
                    'encore': 'BIGINT',
                    'is_cover': 'BOOLEAN',
                    'is_tape': 'BOOLEAN'
                }
            )
        ),
        deduped as (
            select
                *,
                row_number() over (
                    partition by setlist_id, song_name, set_name
                    order by song_name
                ) as rn
            from source
        )
        select
            md5(
                setlist_id || '|' || song_name || '|'
                || coalesce(set_name, '') || '|' || cast(encore as varchar)
            ) as song_id,
            setlist_id,
            song_name,
            set_name,
            encore,
            coalesce(is_cover, false) as is_cover,
            cover_artist_name,
            coalesce(is_tape, false) as is_tape
        from deduped
        where rn = 1
          and (is_tape is null or is_tape = false)
          and song_name is not null
          and song_name != ''
    """,
}

# Mart models — built in dependency order (fct_concerts before dim_bands) --------

MARTS_SQL = {
    "fct_concerts": """
        with songs_agg as (
            select setlist_id, count(*) as song_count
            from staging.stg_songs
            group by 1
        ),
        album_stats as (
            select
                band_id,
                avg(avg_review_pct) as avg_review_score,
                sum(review_count) as review_count
            from staging.stg_albums
            where review_count > 0
            group by 1
        )
        select
            s.setlist_id as concert_id,
            b.band_id as ma_band_id,
            s.artist_name,
            b.primary_subgenre,
            s.event_date,
            s.event_year,
            s.event_month,
            s.venue_name,
            s.city_name,
            s.country_code,
            s.country_name,
            s.latitude,
            s.longitude,
            s.tour_name,
            coalesce(sa.song_count, 0) as song_count,
            ar.avg_review_score,
            ar.review_count
        from staging.stg_setlists s
        inner join staging.stg_band_mapping m on s.artist_mbid = m.sfm_mbid
        inner join staging.stg_bands b on m.ma_band_id = b.band_id
        left join songs_agg sa on s.setlist_id = sa.setlist_id
        left join album_stats ar on b.band_id = ar.band_id
    """,
    "dim_bands": """
        with album_stats as (
            select
                band_id,
                count(*) as total_albums,
                count(*) filter (where album_type = 'Full-length') as full_length_count,
                min(year) as debut_year,
                max(year) - min(year) as career_span_years,
                avg(avg_review_pct) as avg_review_score,
                sum(review_count) as total_reviews
            from staging.stg_albums
            group by 1
        ),
        concert_stats as (
            select ma_band_id, count(*) as total_concerts
            from marts.fct_concerts
            group by 1
        )
        select
            b.band_id as ma_band_id,
            b.band_name,
            b.country,
            b.primary_subgenre,
            b.genre as full_genre,
            b.status,
            m.sfm_mbid,
            m.sfm_mbid is not null as has_setlist_data,
            coalesce(a.total_albums, 0) as total_albums,
            coalesce(a.full_length_count, 0) as full_length_count,
            a.debut_year,
            a.career_span_years,
            case
                when a.band_id is null then 'No releases'
                when a.full_length_count = 0 then 'Demo/EP only'
                when a.full_length_count = 1 then 'One album'
                when a.full_length_count <= 4 then '2-4 albums'
                when a.full_length_count <= 9 then '5-9 albums'
                else '10+ albums'
            end as career_shape,
            a.avg_review_score,
            coalesce(a.total_reviews, 0) as total_reviews,
            coalesce(c.total_concerts, 0) as total_concerts
        from staging.stg_bands b
        left join staging.stg_band_mapping m on b.band_id = m.ma_band_id
        left join album_stats a on b.band_id = a.band_id
        left join concert_stats c on b.band_id = c.ma_band_id
    """,
    # Band x genre-keyword bridge; pages join it to filter any band-keyed table
    # by keyword (e.g. agg_album_reviews) without a dedicated tag-keyed mart.
    "band_genre_tags": """
        select band_id as ma_band_id, genre_tag
        from staging.stg_band_genre_tags
    """,
    "agg_genre_touring_intensity": """
        select
            primary_subgenre,
            count(distinct ma_band_id) as band_count,
            count(*) as total_concerts,
            round(count(*) * 1.0 / count(distinct ma_band_id), 1) as avg_concerts_per_band
        from marts.fct_concerts
        where primary_subgenre is not null and primary_subgenre != ''
        group by primary_subgenre
    """,
    "agg_concerts_over_time": """
        select event_year, event_month, count(*) as concert_count
        from marts.fct_concerts
        group by event_year, event_month
    """,
    "agg_subgenre_share_over_time": """
        with yearly as (
            select event_year, primary_subgenre, count(*) as concert_count
            from marts.fct_concerts
            where primary_subgenre is not null and primary_subgenre != ''
            group by event_year, primary_subgenre
        ),
        yearly_total as (
            select event_year, sum(concert_count) as total
            from yearly
            group by event_year
        )
        select
            y.event_year,
            y.primary_subgenre,
            y.concert_count,
            round(y.concert_count * 100.0 / yt.total, 1) as concert_share_pct
        from yearly y
        inner join yearly_total yt on y.event_year = yt.event_year
    """,
    # Tag counterpart of agg_subgenre_share_over_time. Shares use ALL concerts
    # that year as the denominator; tags overlap (a Progressive Death Metal
    # band counts under both), so a year's shares may sum past 100%.
    "agg_tag_share_over_time": """
        with yearly_total as (
            select event_year, count(*) as total
            from marts.fct_concerts
            group by event_year
        ),
        yearly_tag as (
            select c.event_year, t.genre_tag, count(*) as concert_count
            from marts.fct_concerts c
            inner join staging.stg_band_genre_tags t on c.ma_band_id = t.band_id
            group by c.event_year, t.genre_tag
        )
        select
            y.event_year,
            y.genre_tag,
            y.concert_count,
            round(y.concert_count * 100.0 / yt.total, 1) as concert_share_pct
        from yearly_tag y
        inner join yearly_total yt on y.event_year = yt.event_year
    """,
    "agg_concerts_by_country": """
        select
            country_code,
            country_name,
            count(*) as concert_count,
            avg(latitude) as avg_latitude,
            avg(longitude) as avg_longitude
        from marts.fct_concerts
        where country_code is not null and country_code != ''
        group by country_code, country_name
    """,
    "agg_top_songs": """
        select
            sg.song_name,
            s.artist_name,
            count(*) as performance_count,
            count(distinct s.venue_id) as unique_venue_count
        from staging.stg_songs sg
        inner join staging.stg_setlists s on sg.setlist_id = s.setlist_id
        where sg.song_name is not null and sg.song_name != ''
          -- setlist.fm logs solos, jams, and tape intros as songs
          and not regexp_matches(lower(sg.song_name), 'solos?$')
          and lower(sg.song_name) not in (
            'intro', 'outro', 'jam', 'improvisation', 'encore',
            'soundcheck', 'tuning', 'band introductions'
          )
        group by sg.song_name, s.artist_name
    """,
    "agg_album_reviews": """
        select
            a.band_id as ma_band_id,
            b.band_name,
            b.country,
            b.primary_subgenre,
            d.career_shape,
            a.album_name,
            a.album_type,
            a.year,
            a.review_count,
            a.avg_review_pct
        from staging.stg_albums a
        inner join staging.stg_bands b on a.band_id = b.band_id
        inner join marts.dim_bands d on a.band_id = d.ma_band_id
        where a.review_count > 0
          and a.avg_review_pct is not null
          and b.primary_subgenre is not null
          and b.primary_subgenre != ''
    """,
    "agg_festival_seasonality": """
        select
            event_month,
            case event_month
                when 1 then 'Jan' when 2 then 'Feb' when 3 then 'Mar'
                when 4 then 'Apr' when 5 then 'May' when 6 then 'Jun'
                when 7 then 'Jul' when 8 then 'Aug' when 9 then 'Sep'
                when 10 then 'Oct' when 11 then 'Nov' when 12 then 'Dec'
            end as month_name,
            count(*) as concert_count,
            count(distinct ma_band_id) as unique_bands,
            count(distinct country_code) as unique_countries
        from marts.fct_concerts
        group by event_month
    """,
    "agg_country_genre_affinity": """
        with country_genre as (
            select country, primary_subgenre, count(*) as band_count
            from staging.stg_bands
            where primary_subgenre is not null and primary_subgenre != ''
              and country is not null and country != ''
              and country not in ('Unknown', 'International')
            group by country, primary_subgenre
        ),
        country_total as (
            select country, sum(band_count) as total
            from country_genre
            group by country
        ),
        genre_total as (
            select primary_subgenre, sum(band_count) as total
            from country_genre
            group by primary_subgenre
        ),
        global_total as (
            select sum(band_count) as total from country_genre
        )
        select
            cg.country,
            cg.primary_subgenre,
            cg.band_count,
            ct.total as country_total_bands,
            round(cg.band_count * 100.0 / ct.total, 1) as genre_pct_in_country,
            round(
                (cg.band_count * 1.0 / ct.total) /
                (gt.total * 1.0 / g.total),
                2
            ) as location_quotient
        from country_genre cg
        inner join country_total ct on cg.country = ct.country
        inner join genre_total gt on cg.primary_subgenre = gt.primary_subgenre
        cross join global_total g
        where ct.total >= 50
          and cg.band_count >= 3
    """,
    # Tag counterpart of agg_country_genre_affinity. Denominators count
    # distinct tagged bands (not tag rows), so the location quotient stays
    # valid even though a band can carry several tags.
    "agg_country_tag_affinity": """
        with bands as (
            select distinct b.band_id, b.country
            from staging.stg_bands b
            inner join staging.stg_band_genre_tags t on b.band_id = t.band_id
            where b.country is not null and b.country != ''
              and b.country not in ('Unknown', 'International')
        ),
        country_tag as (
            select b.country, t.genre_tag, count(distinct b.band_id) as band_count
            from bands b
            inner join staging.stg_band_genre_tags t on b.band_id = t.band_id
            group by b.country, t.genre_tag
        ),
        country_total as (
            select country, count(*) as total
            from bands
            group by country
        ),
        tag_total as (
            select genre_tag, sum(band_count) as total
            from country_tag
            group by genre_tag
        ),
        global_total as (
            select count(*) as total from bands
        )
        select
            ct.country,
            ct.genre_tag,
            ct.band_count,
            c.total as country_total_bands,
            round(ct.band_count * 100.0 / c.total, 1) as genre_pct_in_country,
            round(
                (ct.band_count * 1.0 / c.total) /
                (tt.total * 1.0 / g.total),
                2
            ) as location_quotient
        from country_tag ct
        inner join country_total c on ct.country = c.country
        inner join tag_total tt on ct.genre_tag = tt.genre_tag
        cross join global_total g
        where c.total >= 50
          and ct.band_count >= 3
    """,
    "agg_genre_lifecycle": """
        with band_first_album as (
            select band_id, min(year) as debut_year
            from staging.stg_albums
            group by band_id
        ),
        band_genre as (
            select b.band_id, b.primary_subgenre, bfa.debut_year
            from staging.stg_bands b
            inner join band_first_album bfa on b.band_id = bfa.band_id
            where b.primary_subgenre is not null and b.primary_subgenre != ''
              and bfa.debut_year >= 1970 and bfa.debut_year <= 2024
        )
        select debut_year, primary_subgenre, count(*) as new_bands
        from band_genre
        group by debut_year, primary_subgenre
    """,
    # Tag counterpart of agg_genre_lifecycle.
    "agg_tag_lifecycle": """
        with band_first_album as (
            select band_id, min(year) as debut_year
            from staging.stg_albums
            group by band_id
        )
        select bfa.debut_year, t.genre_tag, count(*) as new_bands
        from staging.stg_band_genre_tags t
        inner join band_first_album bfa on t.band_id = bfa.band_id
        where bfa.debut_year >= 1970 and bfa.debut_year <= 2024
        group by bfa.debut_year, t.genre_tag
    """,
    "agg_career_shape": """
        with per_band as (
            select
                b.band_id,
                b.primary_subgenre,
                cast(floor(min(a.year) / 10) * 10 as bigint) as debut_decade,
                count(*) filter (where a.album_type = 'Full-length') as full_lengths,
                sum(a.review_count) as total_reviews,
                sum(a.avg_review_pct * a.review_count) as score_x_reviews
            from staging.stg_albums a
            inner join staging.stg_bands b on a.band_id = b.band_id
            where b.primary_subgenre is not null and b.primary_subgenre != ''
            group by b.band_id, b.primary_subgenre
            having min(a.year) between 1960 and 2025
        )
        select
            primary_subgenre,
            debut_decade,
            case
                when full_lengths = 0 then 'Demo/EP only'
                when full_lengths = 1 then 'One album'
                when full_lengths <= 4 then '2-4 albums'
                when full_lengths <= 9 then '5-9 albums'
                else '10+ albums'
            end as career_shape,
            count(*) as band_count,
            round(sum(score_x_reviews) / nullif(sum(total_reviews), 0), 1)
                as avg_review_score,
            sum(total_reviews) as total_reviews
        from per_band
        group by 1, 2, 3
    """,
    # Tag counterpart of agg_career_shape; bands appear once per tag they carry.
    "agg_career_shape_by_tag": """
        with per_band as (
            select
                a.band_id,
                cast(floor(min(a.year) / 10) * 10 as bigint) as debut_decade,
                count(*) filter (where a.album_type = 'Full-length') as full_lengths,
                sum(a.review_count) as total_reviews,
                sum(a.avg_review_pct * a.review_count) as score_x_reviews
            from staging.stg_albums a
            group by a.band_id
            having min(a.year) between 1960 and 2025
        )
        select
            t.genre_tag,
            p.debut_decade,
            case
                when p.full_lengths = 0 then 'Demo/EP only'
                when p.full_lengths = 1 then 'One album'
                when p.full_lengths <= 4 then '2-4 albums'
                when p.full_lengths <= 9 then '5-9 albums'
                else '10+ albums'
            end as career_shape,
            count(*) as band_count,
            round(sum(p.score_x_reviews) / nullif(sum(p.total_reviews), 0), 1)
                as avg_review_score,
            sum(p.total_reviews) as total_reviews
        from per_band p
        inner join staging.stg_band_genre_tags t on p.band_id = t.band_id
        group by 1, 2, 3
    """,
}

# Tables the dashboard queries; the build fails if any comes out empty.
REQUIRED_TABLES = [
    "dim_bands",
    "fct_concerts",
    "band_genre_tags",
    "agg_tag_share_over_time",
    "agg_country_tag_affinity",
    "agg_tag_lifecycle",
    "agg_career_shape_by_tag",
    "agg_genre_touring_intensity",
    "agg_concerts_over_time",
    "agg_subgenre_share_over_time",
    "agg_concerts_by_country",
    "agg_top_songs",
    "agg_album_reviews",
    "agg_festival_seasonality",
    "agg_country_genre_affinity",
    "agg_genre_lifecycle",
    "agg_career_shape",
]


def resolve_out_path() -> Path:
    out = Path(os.environ.get("DUCKDB_PATH", DEFAULT_OUT))
    if out.stem == "marts":
        # DuckDB names the catalog after the file; a `marts` catalog collides
        # with the `marts` schema and breaks every dashboard query.
        sys.exit("The output file must not be named marts.duckdb — use analytics.duckdb.")
    return out


def build() -> None:
    missing = [str(p) for p in RAW_FILES.values() if not p.exists()]
    if missing:
        sys.exit(
            "Missing raw CSVs (run `make ingest` first):\n  " + "\n  ".join(missing)
        )

    out = resolve_out_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    for stale in (out, out.with_suffix(out.suffix + ".wal")):
        stale.unlink(missing_ok=True)

    con = duckdb.connect()  # staging + marts build in memory
    params = {name: str(path) for name, path in RAW_FILES.items()}

    con.execute("create schema staging")
    for name, sql in STAGING_SQL.items():
        used = {k: v for k, v in params.items() if f"${k}" in sql}
        con.execute(f"create table staging.{name} as {sql}", used)
        n = con.execute(f"select count(*) from staging.{name}").fetchone()[0]
        print(f"  staging.{name}: {n:,} rows")

    con.execute("create schema marts")
    for name, sql in MARTS_SQL.items():
        con.execute(f"create table marts.{name} as {sql}")

    # Persist only the marts schema into a fresh file.
    con.execute(f"attach '{out}' as analytics")
    con.execute("create schema analytics.marts")
    print("marts:")
    for name in MARTS_SQL:
        con.execute(f"create table analytics.marts.{name} as select * from marts.{name}")
        n = con.execute(f"select count(*) from analytics.marts.{name}").fetchone()[0]
        print(f"  marts.{name}: {n:,} rows")
        if name in REQUIRED_TABLES and n == 0:
            sys.exit(f"marts.{name} is empty — the dashboard needs it populated.")
    con.execute("detach analytics")
    con.close()

    size_mb = out.stat().st_size / 1_000_000
    print(f"\nWrote {out} ({size_mb:.1f} MB)")
    if size_mb > 90:
        print("Warning: file exceeds ~90 MB — consider Git LFS before committing.")


if __name__ == "__main__":
    build()
