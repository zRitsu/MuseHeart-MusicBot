import os

from flask import Flask, render_template

app = Flask(__name__)

@app.route('/')
def get_image():
    url = os.environ.get("PROJECT_PREVIEW", "https://cdn.discordapp.com/attachments/480195401543188483/915455362201702420/rec_2021-12-01_01-08-17-563.mp4")
    return render_template('preview.html', url=url)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=80)