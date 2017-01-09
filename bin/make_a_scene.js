#!/usr/bin/env node

const async = require('async')
const request = require('request')

// aws s3 ls s3://oam-dynamic-tiler-tmp/sources/58655b07f91c99bd00e9c7ab/0/ | grep json | grep -v meta | grep -v scene | awk '{print "http://s3.amazonaws.com/oam-dynamic-tiler-tmp/sources/58655b07f91c99bd00e9c7ab/0/"  $4}' | xargs bin/make_a_scene.js | aws s3 cp - s3://oam-dynamic-tiler-tmp/sources/58655b07f91c99bd00e9c7ab/0/scene.json

const scene = {
  // TODO command line arg
  name: 's3://oam-dynamic-tiler-tmp/sources/571ebe60cd0663bb003c3298/0',
  bounds: [Infinity, Infinity, -Infinity, -Infinity],
  minzoom: Infinity,
  meta: {
    // even cooler would be to vectorize the masks and use those for intersections
    //   rio shapes --mask --sampling 100 --precision 6 586b6d05b0eae7f3b143a90e.tif > footprint_100.json
    sources: []
  },
  maxzoom: -Infinity,
  tilejson: '2.1.0'
}

// TODO path prefix as a command line arg
async.each(process.argv.slice(2), (filename, done) => {
  request({
    json: true,
    uri: filename
  }, (err, rsp, body) => {
    if (err) {
      return done(err)
    }

    scene.bounds[0] = Math.min(scene.bounds[0], body.bounds[0])
    scene.bounds[1] = Math.min(scene.bounds[1], body.bounds[1])
    scene.bounds[2] = Math.max(scene.bounds[2], body.bounds[2])
    scene.bounds[3] = Math.max(scene.bounds[3], body.bounds[3])
    scene.minzoom = Math.min(scene.minzoom, body.minzoom)
    scene.maxzoom = Math.max(scene.maxzoom, body.maxzoom)
    delete body.tilejson
    scene.meta.sources.push(body)

    return done()
  })
}, err => {
  if (err) {
    throw err
  }

  const approximateZooms = scene.meta.sources.map(x => x.meta.approximateZoom)
  const avgZoom = approximateZooms.reduce((a, b) => a + b) / approximateZooms.length

  scene.center = [(scene.bounds[0] + scene.bounds[2]) / 2, (scene.bounds[1] + scene.bounds[3]) / 2, Math.floor((scene.minzoom + avgZoom) / 2)]

  process.stdout.write(JSON.stringify(scene))
})
