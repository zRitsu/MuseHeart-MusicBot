cp -n .env-example .env
python -m venv venv
source venv/bin/activate
pip install -U poetry
pip install -r requirements.txt
mkdir ./ffmpeg_temp
curl https://johnvansickle.com/ffmpeg/builds/ffmpeg-git-amd64-static.tar.xz -o ./ffmpeg_temp/ffmpeg.tar.xz
tar -xf ./ffmpeg_temp/ffmpeg.tar.xz --strip-components 1 -C ./ffmpeg_temp
mv ./ffmpeg_temp/ffmpeg ./venv/bin/ffmpeg
rm -rf ./ffmpeg_temp
git clone https://gitlab.xiph.org/xiph/opus.git
cd opus && ./autogen.sh && ./configure && make && cd ..
mkdir ./venv/opus_lib
mv opus/.libs/* venv/opus_lib
rm -rf ./opus
