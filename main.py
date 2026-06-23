import traceback
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont, UnidentifiedImageError
from flask import Flask, make_response, request
from werkzeug.exceptions import HTTPException

from models.queries import fetch_queries

app = Flask(__name__)


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    # TEMPORARY DEBUG AID: surface the real exception and traceback in the
    # response body instead of a generic "Internal Server Error", so failures
    # for specific users can be diagnosed directly on the deployed server
    # (where DEBUG is off and tracebacks are otherwise hidden).
    # NOTE: this exposes internal details to callers -- remove this handler,
    # or gate it behind an env flag, once the root cause is found.
    if isinstance(error, HTTPException):
        return error
    tb = traceback.format_exc()
    app.logger.error("Unhandled error handling %s:\n%s", request.path, tb)
    body = (
        f"Internal error while handling {request.path}\n\n"
        f"{type(error).__name__}: {error}\n\n"
        f"{tb}"
    )
    return make_response(body, 500, {"Content-Type": "text/plain; charset=utf-8"})


# fetch GitHub data
def fetch_github_data(username):
    user_url = f'https://api.github.com/users/{username}'
    commits_url = f'https://api.github.com/search/commits?q=author:{username}'

    try:
        user_response = requests.get(user_url)
        commits_response = requests.get(commits_url)
        user_response.raise_for_status()
        commits_response.raise_for_status()
        user_data = user_response.json()
        commits_data = commits_response.json()
        return user_data, commits_data
    except requests.RequestException as e:
        print("Error fetching GitHub data:", e)
        return None, None


@app.route('/embed/rank/<string:muid>')
def get_muid(muid):
    data = fetch_queries(muid)

    if data:

        # Background image
        image_path = "./assets/images/git.png" if data["github_username"] else "./assets/images/card.png"

        # Profile Pic
        image_url = data["profile_pic"]
        try:
            response = requests.get(image_url)
            response.raise_for_status()
            # Normalise to RGBA: palette ("P") or other modes become "PA"/etc.
            # after putalpha() and make background.paste() raise
            # "bad transparency mask". RGBA keeps the circular alpha mask valid.
            im = Image.open(BytesIO(response.content)).convert("RGBA")
        except (requests.RequestException, UnidentifiedImageError, OSError):
            # The avatar URL may be missing, unreachable, or return a non-image
            # 200 (e.g. an SPA HTML page) -> fall back to a bundled default
            # avatar so the card always renders instead of raising a 500.
            im = Image.open("./assets/images/default_avatar.png").convert("RGBA")

        if im.size[0] < 725 or im.size[1] < 725:
            pass

        im = im.resize((256, 256))

        bigsize = (im.size[0] * 3, im.size[1] * 3)
        mask = Image.new("L", bigsize, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + bigsize, fill=255)
        mask = mask.resize(im.size, Image.LANCZOS)
        im.putalpha(mask)

        im = im.resize((round(im.size[0] * 1.0), round(im.size[1] * 1.0)))

        # fonts
        font_med = "./assets/fonts/PlusJakartaSans-Medium.ttf"
        font_bold = "./assets/fonts/PlusJakartaSans-Bold.ttf"

        # colors
        name_color = "rgb(255, 255, 255)"
        karma_color = "rgb(255, 255, 255)"
        rank_color = "rgb(15, 136, 255)"
        ig_color = "rgb(75, 75, 75)"

        background = Image.open(image_path)
        draw = ImageDraw.Draw(background)

        # Roles
        if data["github_username"]:
            font = ImageFont.truetype(font_bold, size=70)
            draw.text((1, 750), data["main_role"], fill=ig_color, font=font)
        else:
            font = ImageFont.truetype(font_bold, size=70)
            draw.text((1, 425), data["main_role"], fill=ig_color, font=font)

        # Name
        font = ImageFont.truetype(font_med, size=45)
        draw.text((410, 60), data["name"], fill=name_color, font=font)

        # Rank
        x1 = 650
        y1 = 160
        r = str(data["rank"])
        font = ImageFont.truetype(font_bold, size=50)
        offsets = {
            6: (27, 29),
            5: (43, 29),
            4: (56, 29),
            3: (67, 29),
            2: (85, 29),
            1: (93, 29),
        }
        x1_offset, y1_offset = offsets.get(len(r), (0, 0))
        draw.multiline_text(
            (x1 + x1_offset, y1 + y1_offset),
            r,
            fill=rank_color,
            font=font,
            align="left",
        )

        # College
        org_codes = ", ".join(data["org_code"])
        font = ImageFont.truetype(font_med, size=30)
        if data["org_code"]:
            draw.text((410, 115), org_codes, fill=name_color, font=font)

        # Karma
        if int(data["karma"]) >= 1000:
            k_score = int(data["karma"]) / 1000
            f_karma = f"{int(k_score)}K" if int(data["karma"]) % 1000 == 0 else f"{k_score:.1f}K"
        else:
            f_karma = data["karma"]

        x = 410
        y = 160
        font = ImageFont.truetype(font_bold, size=50)

        offsets = {
            6: (17, 29),
            5: (33, 29),
            4: (47, 29),
            3: (65, 29),
            2: (77, 29),
            1: (85, 29),
        }
        x_offset, y_offset = offsets.get(len(f_karma), (0, 0))
        draw.multiline_text(
            (x + x_offset, y + y_offset),
            f_karma,
            fill=karma_color,
            font=font,
            align="left",
        )

        # Interest Groups
        start_position = (407, 340)
        padding = 10
        current_position = start_position
        y = start_position[1]
        x = start_position[0]
        desired_width = 900
        ig_list = data["ig_name"]

        if len(ig_list) > 3:
            font_size = 12
        else:
            font_size = 15

        for ig in ig_list:
            text = ig

            font = ImageFont.truetype(font_med, size=font_size)
            text_width, text_height = font.getsize(text)
            rectangle_width = text_width + 2 * padding
            rectangle_height = 28

            # Checking if the box exceeds the desired width
            if x + rectangle_width > desired_width:
                x = start_position[0]
                y += rectangle_height + 10  # Add vertical spacing between lines of boxes

            # Determine the position of the rounded rectangle
            rectangle_x = x
            rectangle_y = y

            # Draw the rounded rectangular background
            draw.rounded_rectangle(
                [(rectangle_x, rectangle_y), (rectangle_x + rectangle_width, rectangle_y + rectangle_height)],
                radius=5,
                fill=ig_color,
            )

            # Calculate the coordinates to center the text
            text_x = rectangle_x + (rectangle_width - text_width) // 2
            text_y = rectangle_y + (rectangle_height - text_height) // 2

            draw.text((text_x, text_y), text, fill=name_color, font=font)

            x += rectangle_width + 10

        # GitHub details
        if data["github_username"]:
            user_data, commits_data = fetch_github_data(data["github_username"])
            if user_data and commits_data:
                follower_count = user_data.get('followers', 0)
                total_repos = user_data.get('public_repos', 0)
                total_commits = commits_data.get('total_count', 0)

                # Draw details on card
                followers_color = "rgb(151,151,151)"
                userid_color = "rgb(155,153,255)"
                spacing = 15
                userid = "@" + data["github_username"]
                box_color = (81, 81, 117)

                # Draw the rectangular background box for the number of commits
                start_position = (730, 616)
                padding = 10
                current_position = start_position
                y = start_position[1]
                x = start_position[0]
                font = ImageFont.truetype(font_med, size=26)
                commit_width, commit_height = font.getsize(str(total_commits))
                commit_box_width = commit_width + 2 * padding
                commit_box_height = 43

                draw.rounded_rectangle(
                    [(x, y), (x + commit_box_width, y + commit_box_height)],
                    radius=5,
                    fill=box_color,
                )

                text_x = x + (commit_box_width - commit_width) // 2
                text_y = (y - 2) + (commit_box_height - commit_height) // 2

                draw.text((text_x, text_y), str(total_commits), fill=name_color, font=font)

                # Draw the rectangular background box for the number of repositories
                start_position = (430, 616)
                padding = 10
                current_position = start_position
                y = start_position[1]
                x = start_position[0]
                font = ImageFont.truetype(font_med, size=26)
                repo_width, repo_height = font.getsize(str(total_repos))
                repo_box_width = repo_width + 2 * padding
                repo_box_height = 43

                draw.rounded_rectangle(
                    [(x, y), (x + repo_box_width, y + repo_box_height)],
                    radius=5,
                    fill=box_color,
                )

                text_x = x + (repo_box_width - repo_width) // 2
                text_y = (y - 2) + (repo_box_height - repo_height) // 2

                draw.text((text_x, text_y), str(total_repos), fill=name_color, font=font)

                # Draw name
                font = ImageFont.truetype(font_med, size=32)
                draw.text((160, 520), data["name"], fill=name_color, font=font)

                # Draw the text for the user ID
                font = ImageFont.truetype(font_med, size=26)
                draw.text((160, 560), userid, fill=userid_color, font=font)

                # Draw followers
                x1 = 600
                y1 = 517
                f = str(follower_count)
                font = ImageFont.truetype(font_med, size=40)
                offsets = {
                    4: (0, 0),
                    3: (10, 0),
                    2: (22, 0),
                    1: (32, 0),
                }
                x1_offset, y1_offset = offsets.get(len(f), (0, 0))
                draw.multiline_text(
                    (x1 + x1_offset, y1 + y1_offset),
                    f,
                    fill=name_color,
                    font=font,
                    align="left",
                )

        # Save the image
        background.paste(im, (85, 130), im)
        response = make_response()
        image_bytes = BytesIO()
        background.save(image_bytes, format='PNG')
        response.data = image_bytes.getvalue()
        response.headers['Content-Type'] = 'image/png'

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers['Cache-Control'] = 'public, max-age=0'
        return response

    else:
        no_user_image_path = "./assets/images/404card.png"

        # Load the 'no_user' image
        no_user_image = Image.open(no_user_image_path)

        # Create a response for the image
        response = make_response()
        image_bytes = BytesIO()
        no_user_image.save(image_bytes, format='PNG')
        response.data = image_bytes.getvalue()
        response.headers['Content-Type'] = 'image/png'

        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers['Cache-Control'] = 'public, max-age=0'
        return response
