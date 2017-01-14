#!/usr/bin/env node

const url = require('url')

const AWS = require('aws-sdk')
const async = require('async')
const request = require('request')
const yargs = require('yargs')

const S3_BUCKET = 'oin-hotosm'

// bin/copy_metadata.js -u 7 \
//   -s 0 \
//   -i 556f7a49ac00a903002fb016 \
// http://hotosm-oam.s3.amazonaws.com/2015-04-20_dar_river_merged_transparent_mosaic_group1.tif_meta.jso
var argv = yargs.usage('Usage: $0 -u <upload> -s <scene> -i <image> <metadata>')
  .demandOption(['u', 's', 'i'])
  .argv

const S3 = new AWS.S3()

const metaUrl = argv._.shift()
const prefix = `http://oin-hotosm.s3.amazonaws.com/${argv.u}/${argv.s}/${argv.i}`

request.get({
  json: true,
  uri: metaUrl
}, (err, rsp, body) => {
  if (err) {
    throw err
  }

  if (rsp.statusCode !== 200) {
    throw new Error(`Couldn't load ${metaUrl}`)
  }

  return request.head(prefix + '.tif', (err, rsp, _) => {
    if (err) {
      throw err
    }

    // rewrite UUID to point to the new file
    body.uuid = prefix + '.tif'

    // update file_size
    body.file_size = Number(rsp.headers['content-length'])

    // add uploaded_at (date), determined from the source URL
    const { path } = url.parse(metaUrl)
    const parts = path.split('/')
    const uploadDate = parts[2]

    if (uploadDate) {
      body.uploaded_at = new Date(uploadDate)
    }

    // update properties.thumbnail
    body.properties = body.properties || {}
    body.properties.thumbnail = prefix + '_thumb.png'

    // write to new location
    return S3.putObject({
      Bucket: S3_BUCKET,
      Key: `${argv.u}/${argv.s}/${argv.i}_meta.json`,
      Body: JSON.stringify(body),
      ACL: 'public-read'
    }, (err, data) => {
      if (err) {
        throw err
      }

      return request.get({
        json: true,
        uri: prefix + '.json'
      }, (err, rsp, meta) => {
        if (err) {
          throw err
        }

        meta.name = body.title

        return S3.putObject({
          Bucket: S3_BUCKET,
          Key: `${argv.u}/${argv.s}/${argv.i}.json`,
          Body: JSON.stringify(meta),
          ACL: 'public-read'
        }, (err, data) => {
          if (err) {
            throw err
          }
        })
      })
    })
  })
})
