CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE footprints (
    wkb_geometry geometry(MultiPolygon,4326),
    id character varying,
    filename character varying,
    resolution double precision,
    source text,
    url text,
    min_zoom integer,
    max_zoom integer,
    priority integer DEFAULT 0,
    approximate_zoom integer,
    enabled boolean NOT NULL DEFAULT TRUE
);

CREATE INDEX footprints_wkb_geometry_geom_idx ON footprints USING gist (wkb_geometry);
