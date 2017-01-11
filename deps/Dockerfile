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
  mkdir -p /tmp/gdal-dev && \
  curl -L https://github.com/OSGeo/gdal/archive/3288b145e6e966499a961c27636f2c9ea80157c2.tar.gz | tar zxf - -C /tmp/gdal-dev --strip-components=1

# Build + install GDAL

WORKDIR /tmp/gdal-dev/gdal

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
  pip install -U --no-binary :all: https://github.com/mojodna/rasterio/archive/1.0a5+nogil.tar.gz && \
  pip install -U rio-color

# Add GDAL libs to the function zip

WORKDIR /var/task

RUN \
  strip lib/libgdal.so.20.1.0 && \
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
    affine/__init__.pyc \
    cachetools/abc.pyc \
    cachetools/cache.pyc \
    cachetools/func.pyc \
    cachetools/__init__.pyc \
    cachetools/keys.pyc \
    cachetools/lfu.pyc \
    cachetools/lru.pyc \
    cachetools/rr.pyc \
    cachetools/ttl.pyc \
    click/_compat.pyc \
    click/core.pyc \
    click/decorators.pyc \
    click/exceptions.pyc \
    click/formatting.pyc \
    click/globals.pyc \
    click/__init__.pyc \
    click/parser.pyc \
    click/termui.pyc \
    click/types.pyc \
    click/_unicodefun.pyc \
    click/utils.pyc \
    enum/__init__.pyc \
    flask/app.pyc \
    flask/blueprints.pyc \
    flask/cli.pyc \
    flask/_compat.pyc \
    flask/config.pyc \
    flask_cors/core.pyc \
    flask_cors/decorator.pyc \
    flask_cors/extension.pyc \
    flask_cors/__init__.pyc \
    flask_cors/version.pyc \
    flask/ctx.pyc \
    flask/globals.pyc \
    flask/helpers.pyc \
    flask/__init__.pyc \
    flask/json.pyc \
    flask/sessions.pyc \
    flask/signals.pyc \
    flask/templating.pyc \
    flask/wrappers.pyc \
    itsdangerous.pyc \
    jinja2/bccache.pyc \
    jinja2/_compat.pyc \
    jinja2/compiler.pyc \
    jinja2/defaults.pyc \
    jinja2/environment.pyc \
    jinja2/exceptions.pyc \
    jinja2/filters.pyc \
    jinja2/idtracking.pyc \
    jinja2/__init__.pyc \
    jinja2/lexer.pyc \
    jinja2/loaders.pyc \
    jinja2/nodes.pyc \
    jinja2/optimizer.pyc \
    jinja2/parser.pyc \
    jinja2/runtime.pyc \
    jinja2/tests.pyc \
    jinja2/utils.pyc \
    jinja2/visitor.pyc \
    markupsafe/_compat.pyc \
    markupsafe/__init__.pyc \
    markupsafe/_speedups.so \
    mercantile/__init__.pyc \
    numpy/add_newdocs.pyc \
    numpy/compat/__init__.pyc \
    numpy/compat/_inspect.pyc \
    numpy/compat/py3k.pyc \
    numpy/__config__.pyc \
    numpy/core/arrayprint.pyc \
    numpy/core/defchararray.pyc \
    numpy/core/fromnumeric.pyc \
    numpy/core/function_base.pyc \
    numpy/core/getlimits.pyc \
    numpy/core/info.pyc \
    numpy/core/__init__.pyc \
    numpy/core/_internal.pyc \
    numpy/core/machar.pyc \
    numpy/core/memmap.pyc \
    numpy/core/_methods.pyc \
    numpy/core/multiarray.so \
    numpy/core/numeric.pyc \
    numpy/core/numerictypes.pyc \
    numpy/core/records.pyc \
    numpy/core/shape_base.pyc \
    numpy/core/umath.so \
    numpy/ctypeslib.pyc \
    numpy/fft/fftpack_lite.so \
    numpy/fft/fftpack.pyc \
    numpy/fft/helper.pyc \
    numpy/fft/info.pyc \
    numpy/fft/__init__.pyc \
    numpy/_globals.pyc \
    numpy/_import_tools.pyc \
    numpy/__init__.pyc \
    numpy/lib/arraypad.pyc \
    numpy/lib/arraysetops.pyc \
    numpy/lib/arrayterator.pyc \
    numpy/lib/_datasource.pyc \
    numpy/lib/financial.pyc \
    numpy/lib/format.pyc \
    numpy/lib/function_base.pyc \
    numpy/lib/index_tricks.pyc \
    numpy/lib/info.pyc \
    numpy/lib/__init__.pyc \
    numpy/lib/_iotools.pyc \
    numpy/lib/nanfunctions.pyc \
    numpy/lib/npyio.pyc \
    numpy/lib/polynomial.pyc \
    numpy/lib/scimath.pyc \
    numpy/lib/shape_base.pyc \
    numpy/.libs/libgfortran-ed201abd.so.3.0.0 \
    numpy/.libs/libopenblasp-r0-39a31c03.2.18.so \
    numpy/lib/stride_tricks.pyc \
    numpy/lib/twodim_base.pyc \
    numpy/lib/type_check.pyc \
    numpy/lib/ufunclike.pyc \
    numpy/lib/utils.pyc \
    numpy/lib/_version.pyc \
    numpy/linalg/info.pyc \
    numpy/linalg/__init__.pyc \
    numpy/linalg/lapack_lite.so \
    numpy/linalg/linalg.pyc \
    numpy/linalg/_umath_linalg.so \
    numpy/ma/core.pyc \
    numpy/ma/extras.pyc \
    numpy/ma/__init__.pyc \
    numpy/matrixlib/defmatrix.pyc \
    numpy/matrixlib/__init__.pyc \
    numpy/polynomial/chebyshev.pyc \
    numpy/polynomial/hermite_e.pyc \
    numpy/polynomial/hermite.pyc \
    numpy/polynomial/__init__.pyc \
    numpy/polynomial/laguerre.pyc \
    numpy/polynomial/legendre.pyc \
    numpy/polynomial/_polybase.pyc \
    numpy/polynomial/polynomial.pyc \
    numpy/polynomial/polyutils.pyc \
    numpy/random/info.pyc \
    numpy/random/__init__.pyc \
    numpy/random/mtrand.so \
    numpy/testing/decorators.pyc \
    numpy/testing/__init__.pyc \
    numpy/testing/nosetester.pyc \
    numpy/testing/utils.pyc \
    numpy/version.pyc \
    PIL/_binary.pyc \
    PIL/BmpImagePlugin.pyc \
    PIL/GifImagePlugin.pyc \
    PIL/GimpGradientFile.pyc \
    PIL/GimpPaletteFile.pyc \
    PIL/ImageChops.pyc \
    PIL/ImageColor.pyc \
    PIL/ImageFile.pyc \
    PIL/ImageMode.pyc \
    PIL/ImagePalette.pyc \
    PIL/Image.pyc \
    PIL/ImageSequence.pyc \
    PIL/_imaging.so \
    PIL/__init__.pyc \
    PIL/JpegImagePlugin.pyc \
    PIL/JpegPresets.pyc \
    PIL/.libs/libjpeg-bcb94a84.so.9.2.0 \
    PIL/.libs/liblzma-f444c404.so.5.2.2 \
    PIL/.libs/libopenjp2-59185378.so.2.1.0 \
    PIL/.libs/libtiff-56518a27.so.5.2.5 \
    PIL/.libs/libz-a147dcb0.so.1.2.3 \
    PIL/PaletteFile.pyc \
    PIL/PngImagePlugin.pyc \
    PIL/PpmImagePlugin.pyc \
    PIL/TiffImagePlugin.pyc \
    PIL/TiffTags.pyc \
    PIL/_util.pyc \
    rasterio/_base.so \
    rasterio/compat.pyc \
    rasterio/control.pyc \
    rasterio/coords.pyc \
    rasterio/crs.pyc \
    rasterio/_crs.so \
    rasterio/drivers.pyc \
    rasterio/_drivers.so \
    rasterio/dtypes.pyc \
    rasterio/enums.pyc \
    rasterio/env.pyc \
    rasterio/errors.pyc \
    rasterio/_err.so \
    rasterio/__init__.pyc \
    rasterio/io.pyc \
    rasterio/_io.so \
    rasterio/profiles.pyc \
    rasterio/sample.pyc \
    rasterio/transform.pyc \
    rasterio/vfs.pyc \
    rasterio/windows.pyc \
    requests/adapters.pyc \
    requests/api.pyc \
    requests/auth.pyc \
    requests/certs.pyc \
    requests/compat.pyc \
    requests/cookies.pyc \
    requests/exceptions.pyc \
    requests/hooks.pyc \
    requests/__init__.pyc \
    requests/_internal_utils.pyc \
    requests/models.pyc \
    requests/packages/chardet/__init__.pyc \
    requests/packages/idna/core.pyc \
    requests/packages/idna/idnadata.pyc \
    requests/packages/idna/__init__.pyc \
    requests/packages/idna/intranges.pyc \
    requests/packages/idna/uts46data.pyc \
    requests/packages/__init__.pyc \
    requests/packages/urllib3/_collections.pyc \
    requests/packages/urllib3/connectionpool.pyc \
    requests/packages/urllib3/connection.pyc \
    requests/packages/urllib3/contrib/__init__.pyc \
    requests/packages/urllib3/contrib/pyopenssl.pyc \
    requests/packages/urllib3/contrib/socks.pyc \
    requests/packages/urllib3/exceptions.pyc \
    requests/packages/urllib3/fields.pyc \
    requests/packages/urllib3/filepost.pyc \
    requests/packages/urllib3/__init__.pyc \
    requests/packages/urllib3/packages/__init__.pyc \
    requests/packages/urllib3/packages/ordered_dict.pyc \
    requests/packages/urllib3/packages/six.pyc \
    requests/packages/urllib3/packages/ssl_match_hostname/_implementation.pyc \
    requests/packages/urllib3/packages/ssl_match_hostname/__init__.pyc \
    requests/packages/urllib3/poolmanager.pyc \
    requests/packages/urllib3/request.pyc \
    requests/packages/urllib3/response.pyc \
    requests/packages/urllib3/util/connection.pyc \
    requests/packages/urllib3/util/__init__.pyc \
    requests/packages/urllib3/util/request.pyc \
    requests/packages/urllib3/util/response.pyc \
    requests/packages/urllib3/util/retry.pyc \
    requests/packages/urllib3/util/ssl_.pyc \
    requests/packages/urllib3/util/timeout.pyc \
    requests/packages/urllib3/util/url.pyc \
    requests/sessions.pyc \
    requests/status_codes.pyc \
    requests/structures.pyc \
    requests/utils.pyc \
    rio_color/colorspace.so \
    rio_color/__init__.pyc \
    rio_color/operations.pyc \
    rio_color/utils.pyc \
    werkzeug/_compat.pyc \
    werkzeug/datastructures.pyc \
    werkzeug/debug/console.pyc \
    werkzeug/debug/__init__.pyc \
    werkzeug/debug/repr.pyc \
    werkzeug/debug/tbtools.pyc \
    werkzeug/exceptions.pyc \
    werkzeug/filesystem.pyc \
    werkzeug/formparser.pyc \
    werkzeug/http.pyc \
    werkzeug/__init__.pyc \
    werkzeug/_internal.pyc \
    werkzeug/local.pyc \
    werkzeug/_reloader.pyc \
    werkzeug/routing.pyc \
    werkzeug/security.pyc \
    werkzeug/serving.pyc \
    werkzeug/test.pyc \
    werkzeug/urls.pyc \
    werkzeug/utils.pyc \
    werkzeug/wrappers.pyc \
    werkzeug/wsgi.pyc \
    raven/* \
    contextlib2.pyc \
    flask/testing.pyc \
    werkzeug/test.pyc
