FROM lambci/lambda:build-python2.7

# Install deps

RUN \
  yum install -y \
    automake16 \
    libcurl-devel \
    libjpeg-turbo-devel \
    libpng-devel

# Fetch PROJ.4

RUN \
  curl -L http://download.osgeo.org/proj/proj-4.9.3.tar.gz | tar zxf - -C /tmp

# Build and install PROJ.4

WORKDIR /tmp/proj-4.9.3

RUN \
  ./configure \
    --prefix=/var/task && \
  make -j $(nproc) && \
  make install

# Fetch GDAL

RUN \
  curl -L http://download.osgeo.org/gdal/2.1.2/gdal-2.1.2.tar.gz | tar zxf - -C /tmp

# Build + install GDAL

WORKDIR /tmp/gdal-2.1.2

RUN \
  ./configure \
    --prefix=/var/task \
    --datarootdir=/var/task/share/gdal \
    --without-qhull \
    --without-mrf \
    --without-grib \
    --without-pcraster \
    --without-png \
    --without-gif \
    --without-pcidsk && \
  make -j $(nproc) && \
  make install

# Install Python deps in a virtualenv

RUN \
  virtualenv /tmp/virtualenv

ENV PATH /tmp/virtualenv/bin:/var/task/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

RUN \
  pip install -U cachetools Cython flask flask_cors jinja2 mercantile numpy pillow raven requests werkzeug && \
  pip install -U --no-binary :all: https://github.com/mojodna/rasterio/archive/1.0a5+nogil.tar.gz

# Add GDAL libs to the function zip

WORKDIR /var/task

RUN \
  strip lib/libgdal.so.20.1.2 && \
  strip lib/libproj.so.12.0.0

RUN \
  zip --symlinks \
    -r /tmp/task.zip \
    lib/libgdal.so* \
    lib/libproj.so* \
    share/gdal/

# Add Python deps to the function zip

WORKDIR /tmp/virtualenv/lib/python2.7/site-packages

# skip the zipping (above, too) and put it in a staging directory that can be copied to a volume or output via tar on stdout
# determined by copying the app in, touching start, exercising it, then using find /tmp/virtualenv/lib/python2.7/site-packages -type f -anewer start
RUN \
  zip \
    -r /tmp/task.zip \
    markupsafe/_compat.pyc \
    markupsafe/_speedups.so \
    markupsafe/__init__.pyc \
    itsdangerous.pyc \
    flask_cors/decorator.pyc \
    flask_cors/core.pyc \
    flask_cors/version.pyc \
    flask_cors/__init__.pyc \
    flask_cors/extension.pyc \
    click/termui.pyc \
    click/utils.pyc \
    click/types.pyc \
    click/parser.pyc \
    click/decorators.pyc \
    click/_compat.pyc \
    click/core.pyc \
    click/_unicodefun.pyc \
    click/exceptions.pyc \
    click/globals.pyc \
    click/formatting.pyc \
    click/__init__.pyc \
    enum/__init__.pyc \
    rasterio/__init__.pyc \
    rasterio/dtypes.pyc \
    rasterio/profiles.pyc \
    rasterio/env.pyc \
    rasterio/transform.pyc \
    rasterio/crs.pyc \
    rasterio/vfs.pyc \
    rasterio/sample.pyc \
    rasterio/drivers.pyc \
    rasterio/compat.pyc \
    rasterio/_drivers.so \
    rasterio/_io.so \
    rasterio/_crs.so \
    rasterio/coords.pyc \
    rasterio/enums.pyc \
    rasterio/control.pyc \
    rasterio/_err.so \
    rasterio/windows.pyc \
    rasterio/_base.so \
    rasterio/io.pyc \
    rasterio/errors.pyc \
    numpy/ctypeslib.pyc \
    numpy/_import_tools.pyc \
    numpy/compat/py3k.pyc \
    numpy/compat/_inspect.pyc \
    numpy/compat/__init__.pyc \
    numpy/lib/arraypad.pyc \
    numpy/lib/info.pyc \
    numpy/lib/polynomial.pyc \
    numpy/lib/index_tricks.pyc \
    numpy/lib/function_base.pyc \
    numpy/lib/_iotools.pyc \
    numpy/lib/ufunclike.pyc \
    numpy/lib/_datasource.pyc \
    numpy/lib/type_check.pyc \
    numpy/lib/twodim_base.pyc \
    numpy/lib/financial.pyc \
    numpy/lib/stride_tricks.pyc \
    numpy/lib/npyio.pyc \
    numpy/lib/nanfunctions.pyc \
    numpy/lib/_version.pyc \
    numpy/lib/scimath.pyc \
    numpy/lib/utils.pyc \
    numpy/lib/format.pyc \
    numpy/lib/__init__.pyc \
    numpy/lib/arraysetops.pyc \
    numpy/lib/arrayterator.pyc \
    numpy/lib/shape_base.pyc \
    numpy/ma/extras.pyc \
    numpy/ma/__init__.pyc \
    numpy/ma/core.pyc \
    numpy/__init__.pyc \
    numpy/core/defchararray.pyc \
    numpy/core/getlimits.pyc \
    numpy/core/_methods.pyc \
    numpy/core/function_base.pyc \
    numpy/core/memmap.pyc \
    numpy/core/_internal.pyc \
    numpy/core/shape_base.pyc \
    numpy/core/multiarray.so \
    numpy/core/machar.pyc \
    numpy/core/info.pyc \
    numpy/core/fromnumeric.pyc \
    numpy/core/records.pyc \
    numpy/core/__init__.pyc \
    numpy/core/umath.so \
    numpy/core/numeric.pyc \
    numpy/core/numerictypes.pyc \
    numpy/core/arrayprint.pyc \
    numpy/random/info.pyc \
    numpy/random/mtrand.so \
    numpy/random/__init__.pyc \
    numpy/polynomial/chebyshev.pyc \
    numpy/polynomial/_polybase.pyc \
    numpy/polynomial/legendre.pyc \
    numpy/polynomial/laguerre.pyc \
    numpy/polynomial/hermite.pyc \
    numpy/polynomial/polyutils.pyc \
    numpy/polynomial/__init__.pyc \
    numpy/polynomial/hermite_e.pyc \
    numpy/polynomial/polynomial.pyc \
    numpy/matrixlib/defmatrix.pyc \
    numpy/matrixlib/__init__.pyc \
    numpy/add_newdocs.pyc \
    numpy/__config__.pyc \
    numpy/linalg/lapack_lite.so \
    numpy/linalg/_umath_linalg.so \
    numpy/linalg/linalg.pyc \
    numpy/linalg/info.pyc \
    numpy/linalg/__init__.pyc \
    numpy/_globals.pyc \
    numpy/.libs/libopenblasp-r0-39a31c03.2.18.so \
    numpy/.libs/libgfortran-ed201abd.so.3.0.0 \
    numpy/version.pyc \
    numpy/fft/fftpack_lite.so \
    numpy/fft/helper.pyc \
    numpy/fft/info.pyc \
    numpy/fft/__init__.pyc \
    numpy/fft/fftpack.pyc \
    numpy/testing/decorators.pyc \
    numpy/testing/nosetester.pyc \
    numpy/testing/__init__.pyc \
    numpy/testing/utils.pyc \
    cachetools/func.pyc \
    cachetools/lfu.pyc \
    cachetools/ttl.pyc \
    cachetools/__init__.pyc \
    cachetools/lru.pyc \
    cachetools/rr.pyc \
    cachetools/keys.pyc \
    cachetools/abc.pyc \
    cachetools/cache.pyc \
    flask/app.pyc \
    flask/ctx.pyc \
    flask/_compat.pyc \
    flask/blueprints.pyc \
    flask/signals.pyc \
    flask/json.pyc \
    flask/helpers.pyc \
    flask/templating.pyc \
    flask/sessions.pyc \
    flask/globals.pyc \
    flask/cli.pyc \
    flask/wrappers.pyc \
    flask/__init__.pyc \
    flask/config.pyc \
    werkzeug/urls.pyc \
    werkzeug/utils.pyc \
    werkzeug/filesystem.pyc \
    werkzeug/datastructures.pyc \
    werkzeug/debug/repr.pyc \
    werkzeug/debug/__init__.pyc \
    werkzeug/debug/console.pyc \
    werkzeug/debug/tbtools.pyc \
    werkzeug/_reloader.pyc \
    werkzeug/_internal.pyc \
    werkzeug/_compat.pyc \
    werkzeug/__init__.pyc \
    werkzeug/exceptions.pyc \
    werkzeug/wrappers.pyc \
    werkzeug/serving.pyc \
    werkzeug/routing.pyc \
    werkzeug/security.pyc \
    werkzeug/formparser.pyc \
    werkzeug/wsgi.pyc \
    werkzeug/local.pyc \
    werkzeug/http.pyc \
    affine/__init__.pyc \
    PIL/PngImagePlugin.pyc \
    PIL/JpegImagePlugin.pyc \
    PIL/_util.pyc \
    PIL/ImageSequence.pyc \
    PIL/PaletteFile.pyc \
    PIL/ImageColor.pyc \
    PIL/TiffTags.pyc \
    PIL/_imaging.so \
    PIL/TiffImagePlugin.pyc \
    PIL/ImageFile.pyc \
    PIL/GimpPaletteFile.pyc \
    PIL/Image.pyc \
    PIL/_binary.pyc \
    PIL/ImageChops.pyc \
    PIL/ImagePalette.pyc \
    PIL/GifImagePlugin.pyc \
    PIL/.libs/libjpeg-bcb94a84.so.9.2.0 \
    PIL/.libs/libtiff-56518a27.so.5.2.5 \
    PIL/.libs/libz-a147dcb0.so.1.2.3 \
    PIL/.libs/libopenjp2-59185378.so.2.1.0 \
    PIL/.libs/liblzma-f444c404.so.5.2.2 \
    PIL/BmpImagePlugin.pyc \
    PIL/ImageMode.pyc \
    PIL/__init__.pyc \
    PIL/GimpGradientFile.pyc \
    PIL/JpegPresets.pyc \
    PIL/PpmImagePlugin.pyc \
    jinja2/lexer.pyc \
    jinja2/compiler.pyc \
    jinja2/_compat.pyc \
    jinja2/visitor.pyc \
    jinja2/environment.pyc \
    jinja2/ext.pyc \
    jinja2/filters.pyc \
    jinja2/optimizer.pyc \
    jinja2/tests.pyc \
    jinja2/exceptions.pyc \
    jinja2/utils.pyc \
    jinja2/loaders.pyc \
    jinja2/runtime.pyc \
    jinja2/nodes.pyc \
    jinja2/__init__.pyc \
    jinja2/defaults.pyc \
    jinja2/bccache.pyc \
    jinja2/parser.pyc \
    mercantile/__init__.pyc \
    requests/__init__.pyc \
    requests/models.pyc \
    requests/cacert.pem \
    requests/hooks.pyc \
    requests/api.pyc \
    requests/sessions.pyc \
    requests/certs.pyc \
    requests/_internal_utils.pyc \
    requests/compat.pyc \
    requests/packages/__init__.pyc \
    requests/packages/urllib3/response.pyc \
    requests/packages/urllib3/poolmanager.pyc \
    requests/packages/urllib3/_collections.pyc \
    requests/packages/urllib3/exceptions.pyc \
    requests/packages/urllib3/filepost.pyc \
    requests/packages/urllib3/util/response.pyc \
    requests/packages/urllib3/util/url.pyc \
    requests/packages/urllib3/util/timeout.pyc \
    requests/packages/urllib3/util/connection.pyc \
    requests/packages/urllib3/util/ssl_.pyc \
    requests/packages/urllib3/util/__init__.pyc \
    requests/packages/urllib3/util/retry.pyc \
    requests/packages/urllib3/util/request.pyc \
    requests/packages/urllib3/connectionpool.pyc \
    requests/packages/urllib3/request.pyc \
    requests/packages/urllib3/connection.pyc \
    requests/packages/urllib3/__init__.pyc \
    requests/packages/urllib3/packages/six.pyc \
    requests/packages/urllib3/packages/ordered_dict.pyc \
    requests/packages/urllib3/packages/__init__.pyc \
    requests/packages/urllib3/packages/ssl_match_hostname/_implementation.pyc \
    requests/packages/urllib3/packages/ssl_match_hostname/__init__.pyc \
    requests/packages/urllib3/contrib/pyopenssl.pyc \
    requests/packages/urllib3/contrib/__init__.pyc \
    requests/packages/urllib3/contrib/socks.pyc \
    requests/packages/urllib3/fields.pyc \
    requests/packages/idna/core.pyc \
    requests/packages/idna/__init__.pyc \
    requests/packages/idna/intranges.pyc \
    requests/packages/idna/idnadata.pyc \
    requests/packages/idna/uts46data.pyc \
    requests/packages/chardet/__init__.pyc \
    requests/structures.pyc \
    requests/adapters.pyc \
    requests/cookies.pyc \
    requests/status_codes.pyc \
    requests/exceptions.pyc \
    requests/auth.pyc \
    requests/utils.pyc \
    raven/* \
    contextlib2.pyc \
    flask/testing.pyc \
    werkzeug/test.pyc
