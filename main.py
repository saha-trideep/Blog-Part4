import os
import smtplib

from flask import Flask, render_template, redirect, url_for, flash, request, send_from_directory
from flask_bootstrap import Bootstrap4
from flask_ckeditor import CKEditor
from datetime import date
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import gunicorn
from sqlalchemy.exc import IntegrityError
from click.core import ParameterSource

from sqlalchemy.orm import relationship
from flask_login import UserMixin, login_user, LoginManager, login_required, current_user, logout_user
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm, AccountForm
from flask_gravatar import Gravatar
from functools import wraps


app = Flask(__name__)
app.config['SECRET_KEY'] = "SECRET_KEY"

Bootstrap4(app)
ckeditor = CKEditor(app)
# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = 'DATABASE_URI'
# app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///user.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['CKEDITOR_SERVE_LOCAL'] = True
app.config['CKEDITOR_HEIGHT'] = 400
# app.config['CKEDITOR_FILE_UPLOADER'] = 'upload'

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.session_protection = 'strong'



gravatar = Gravatar(
    app,
    size=100,
    rating='g',
    default='retro',
    force_default=False,
    force_lower=False,
    use_ssl=False,
    base_url=None

)

from_address = os.getenv('FROM_ADDRESS')
password = os.getenv('PASSWORD')
to_address = os.getenv('TO_ADDRESS')


# CONFIGURE TABLES
class User(UserMixin, db.Model):
    __tablename__ = "user_details"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    name = db.Column(db.String(100))
    password = db.Column(db.String(100))
    is_admin = db.Column(db.Boolean, default=False)

    # Parent(BlogPost)
    posts = relationship('BlogPost', back_populates='author')
    # Parent(Comment)
    comments = relationship('Comment', back_populates='commenter')

    # Password setting
    def set_password(self, password):
        self.password = generate_password_hash(password=password, method='pbkdf2:sha256', salt_length=8)

    def check_password(self, password):
        return check_password_hash(self.password, password=password)


class BlogPost(db.Model):
    __tablename__ = "blog_posts"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    img_url = db.Column(db.String(250), nullable=False)

    # Child(User)
    author_id = db.Column(db.Integer, db.ForeignKey('user_details.id'))
    author = relationship('User', back_populates='posts')
    # Parent(Comment)
    all_comments = relationship('Comment', back_populates='parent_post')


class Comment(db.Model):
    __tablename__ = "comments"

    id = db.Column(db.Integer, primary_key=True)
    area = db.Column(db.String, nullable=False)

    # Child(User)
    author_id = db.Column(db.Integer, db.ForeignKey('user_details.id'))
    commenter = relationship('User', back_populates='comments')
    # Child(BlogPost)
    post_id = db.Column(db.Integer, db.ForeignKey('blog_posts.id'))
    parent_post = relationship('BlogPost', back_populates='all_comments')


# with app.app_context():
#     db.create_all()


def admin_only(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_admin:
            return redirect(url_for('/register'))
        return f(*args, **kwargs)

    return decorated_function


@login_manager.user_loader
def user_load(user_id):
    return User.query.get(user_id)


@app.route('/')
def get_all_posts():
    posts = BlogPost.query.all()
    return render_template("index.html", all_posts=posts)


@app.route('/register', methods=['GET', 'POST'])
def register():
    reg_form = RegisterForm()
    if reg_form.validate_on_submit():
        try:
            user = User()
            user.email = reg_form.email.data
            user.name = reg_form.name.data
            user.set_password(reg_form.password.data)
            db.session.add(user)
            db.session.commit()

            login_user(user)

            if current_user.id:
                user.is_admin = True
            return redirect(url_for('get_all_posts'))

        except IntegrityError:
            flash('You have already sign up with this email. log in instead!')
            return redirect(url_for('login'))
    return render_template("register.html", form=reg_form)


@app.route('/login', methods=['GET', 'POST'])
def login():
    login_form = LoginForm()
    if login_form.validate_on_submit():
        user = User.query.filter_by(email=login_form.email.data).first()
        if user is None:
            user = User()
            user.email = login_form.email.data
            user.name = 'New user'
            user.set_password(login_form.password.data)
            user.is_admin = False
            db.session.add(user)
            db.session.commit()
            login_user(user)
            return redirect(url_for('get_all_posts', current_user=user))

        else:
            if user.email != login_form.email.data:
                flash('May be this email address incorrect! Please try again.')
            elif not user.check_password(login_form.password.data):
                flash('May be password incorrect! Sorry.')

            else:
                login_user(user)
                return redirect(url_for('get_all_posts', current_user=current_user))

    return render_template("login.html", form=login_form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route("/post/<int:post_id>", methods=['GET', 'POST'])
def show_post(post_id):
    requested_post = BlogPost.query.get(post_id)
    all_comments = Comment.query.all()
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if not current_user.is_authenticated:
            flash('You need to login or register to comment.')
            return redirect(url_for('login'))
        else:
            comment = Comment()
            comment.area = comment_form.text.data
            comment.commenter = current_user
            comment.parent_post = requested_post
            db.session.add(comment)
            db.session.commit()
            return redirect(url_for('show_post', post_id=post_id))

    return render_template("post.html", post=requested_post, comments_form=comment_form, current_user=current_user,
                           all_comments=all_comments, today=date.today().strftime("%a, %b%y"))


@app.route("/account/<int:my_id>", methods=["GET", "POST"])
@login_required
def my_account(my_id):
    user_account = User.query.filter_by(id=my_id).first()
    account_form = AccountForm(
        name=user_account.name,
        password=user_account.password,
    )
    if account_form.validate_on_submit():
        user = User.query.get(my_id)
        user.name = account_form.name.data
        user.set_password(account_form.password.data)
        db.session.commit()
        flash(f'Hey, {user.name};  your name & password has been changed.')
        return redirect(url_for('my_account', my_id=my_id, name=user.name))

    return render_template('my_account.html', form=account_form)


@app.route('/comment_delete_confirm/<int:comment_id>')
@login_required
@admin_only
def comment_delete_confirm(comment_id):
    selected_comment = Comment.query.filter_by(id=comment_id).first()

    return render_template('delete_comment.html', comment=selected_comment)


@app.route('/delete_comment/<int:author_id>', methods=["POST"])
@login_required
@admin_only
def delete_comment(author_id):
    select_comment = Comment.query.filter_by(id=author_id).first()
    db.session.delete(select_comment)
    db.session.commit()
    flash('Message deleted successfully.')
    return redirect(url_for('show_post', post_id=author_id))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact", methods=["GET", "POST"])
def contact():
    if not current_user.is_authenticated:
        flash('Click the below link')
        return render_template('401.html'), 401
    # if request.method == "POST":
    #     user_name = request.form.get('name')
    #     user_email = request.form.get('email')
    #     user_phone = request.form.get('phone')
    #     user_message = request.form.get('message')
    #     try:
    #         with smtplib.SMTP('smtp.gmail.com') as connection:
    #             connection.starttls()
    #             connection.login(user=from_address, password=password)
    #             connection.sendmail(
    #                 from_addr=from_address,
    #                 to_addrs=to_address,
    #                 msg=f"Subject:Blog Response\n\nName:{user_name}\nEmail:{user_email}\n"
    #                     f"Phone:{user_phone}\nMessage:'''{user_message}'''"
    #             )
    #
    #             flash('Thank you! Message send successfully.')
    #             redirect(url_for('get_all_posts'))
    #     except smtplib.SMTPException as e:
    #         flash(f"An error occurred")
    #         redirect(url_for('contact'))
    return render_template("contact.html")


@app.route("/new-post", methods=['GET', 'POST'])
@login_required
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit() and request.method == 'POST':
        if current_user.is_authenticated:
            new_post = BlogPost(
                title=form.title.data,
                subtitle=form.subtitle.data,
                body=form.body.data,
                img_url=form.img_url.data,
                author=current_user,
                date=date.today().strftime("%B %d, %Y")
            )
            db.session.add(new_post)
            db.session.commit()
            return redirect(url_for("get_all_posts"))
        else:
            flash('Want to create Blog, Please register!')
            redirect(url_for('register'))
    return render_template("make-post.html", form=form)


# @app.route('/files/<filename>')
# def uploaded_files(filename):
#     path = '/static/ckeditor'
#     return send_from_directory(directory=path, path=filename)
#
#
# @app.route('/upload', methods=['POST'])
# @ckeditor.uploader
# def upload():
#     f = request.files.get('upload')
#     f.save(os.path.join('/static/ckeditor', f.filename))
#     url = url_for('uploaded_files', filename=f.filename)
#     return url


@app.route("/edit-post/<int:post_id>", methods=['GET', 'POST'])
@login_required
@admin_only
def edit_post(post_id):
    post = BlogPost.query.get(post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=current_user.name,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data

        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))

    return render_template("make-post.html", form=edit_form, is_edit=True, id=post_id)


@app.route("/delete/<int:post_id>")
@login_required
@admin_only
def delete_post(post_id):
    post_to_delete = BlogPost.query.get(post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


if __name__ == '__main__':
    app.run()
