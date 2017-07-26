-- Uses builtin PostGIS functionality to generate a GeoJSON FeatureCollection
-- of all the footprints in the database. To get a GeoJSON file without
-- any psql cruft, run something like this:
--
-- psql postgresql://user:password@database.host/footprints \
--      -t --pset="footer=off" \
--      -f footprints_to_geojson.sql \
--      > footprints.geojson

SELECT row_to_json(featcoll)
FROM (
    SELECT 'FeatureCollection' As type, array_to_json(array_agg(feat)) As features
    FROM (
        SELECT 'Feature' As type,
               ST_AsGeoJSON(tbl.wkb_geometry, 6)::json As geometry,
               row_to_json((SELECT l FROM (SELECT id, filename, resolution, source, url, min_zoom, max_zoom, priority, approximate_zoom) As l)) As properties
        FROM footprints As tbL
        WHERE enabled
    ) As feat
) As featcoll;
