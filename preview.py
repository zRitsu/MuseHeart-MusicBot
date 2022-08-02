import os

from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def get_image():
    return render_template('preview.html', video_preview=os.environ["VIDEO_PREVIEW"])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)
