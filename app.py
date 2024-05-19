from flask import Flask, Response, render_template, send_from_directory, jsonify, request, redirect, url_for, abort
from flask_login import UserMixin, LoginManager, login_user, logout_user, login_required, current_user
from flask_admin import Admin, AdminIndexView, helpers, expose
from flask_admin.contrib.sqla import ModelView
from flask_admin.form.upload import ImageUploadField
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.hybrid import hybrid_property
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os, re, random
from style import blog
from utils import readingTime, get_img, get_sub_title, get_id, get_url, check_url, add_ellipsis, get_url_by_name
from readMarkdown import  extract_markdown
import uuid
from urllib.parse import urlparse

# global variables
DEFAULT = None
basedir = os.path.abspath(os.path.dirname(__file__))

# flask variables
app = Flask(__name__)

DEBUG = False
RESET = False
PRODUCTION_VERSION = True
TESTING = False

if TESTING:
    from dotenv import load_dotenv
    # Load environment variables from .env file
    load_dotenv()

if not PRODUCTION_VERSION and not os.path.exists(os.path.join(basedir, 'database')): os.mkdir(os.path.join(basedir, 'database'))

if PRODUCTION_VERSION:
    # Access the environment variables
    hostname = os.getenv("db_hostname")
    port = int(os.getenv("db_port"))
    database = os.getenv("db_database")
    username = os.getenv("db_username")
    password = os.getenv("db_password")
    app.config['SQLALCHEMY_DATABASE_URI'] = f'postgresql://{username}:{password}@{hostname}:{port}/{database}?sslmode=require'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database\\database.db')

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config["NOT_SECRET_KEY"] = os.getenv("NOT_SECRET_KEY")
app.config['MAX_CONTENT_LENGTH'] = 16 * 1000 * 1000 # MAX PAYLOAD size is 16 MB else raise  RequestEntityTooLarge    
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app) # Creating an SQLAlchemy instance

login_manager = LoginManager()
# login_manager.login_view = 'auth.login'
login_manager.init_app(app)

class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if current_user.is_authenticated and current_user.is_admin:
            return super(MyAdminIndexView, self).index()
        return redirect(url_for('login'))

adminPanel = Admin(app, 'AdminPanel', index_view=MyAdminIndexView(), template_mode='bootstrap4', url='/admin', base_template='my_master.html')

def addModel(model): 
    adminPanel.add_view(ModelView(model, db.session))
    return model


@addModel
class Tag(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True)
    # repr method represents how one object of this datatable will look like
    def __repr__(self):
        return f"Tag({self.name})"


def find_or_create_tag(name:str):
    name = get_url_by_name(name).replace('_', ' ')
    # Search for the tag in the database
    tag = Tag.query.filter_by(name=name).first()
    
    if tag is None:
        # If the tag doesn't exist, create a new one
        tag = Tag(name=name)
        db.session.add(tag)
        db.session.commit()
    
    return tag

# Association Table
blog_tag_association = db.Table('blog_tag_association',
    db.Column('blog_id', db.Integer, db.ForeignKey('blog.id')),
    db.Column('tag_id', db.Integer, db.ForeignKey('tag.id'))
)

class Blog(db.Model):
    # Id : Field which stores unique id for every row in 
    id = db.Column(db.Integer, primary_key=True)
    
    title = db.Column(db.String(100), unique=False, nullable=False)
    description = db.Column(db.String(100), unique=False, nullable=True)
    data = db.Column(db.Text, unique=False, nullable=False)
    date_posted = db.Column(db.DateTime, nullable=False, default=datetime.now)
    time_read = db.Column(db.Integer, nullable=True)
    
    claps = db.Column(db.Integer, nullable=False, default=0)
        
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    tags = db.relationship('Tag', secondary=blog_tag_association, backref='blogs', lazy='dynamic')


    # repr method represents how one object of this datatable will look like
    def __repr__(self):
        return f"Blog({self.id}, {self.user_id}, {self.title}, {self.description})"

class CustomBlogView(ModelView):
    # Customize the columns displayed on the list view
    column_list = ('id', 'title', 'description', 'date_posted', 'time_read', 'claps', 'author')

# Register the custom view for the Blog model with Flask-Admin
adminPanel.add_view(CustomBlogView(Blog, db.session))

# Association table for the many-to-many relationship between User and Blog for saved blogs
saved_blogs = db.Table('saved_blogs',
    db.Column('user_id', db.Integer, db.ForeignKey('user.id'), primary_key=True),
    db.Column('blog_id', db.Integer, db.ForeignKey('blog.id'), primary_key=True)
)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    userName = db.Column(db.String(250), unique=True, nullable=False)
    email = db.Column(db.String(250), unique=True, nullable=False)
    password = db.Column(db.String(250), nullable=False)
    userDescription = db.Column(db.String(300), unique=False, nullable=True)
    userPNG = db.Column(db.String(100), unique=False, nullable=True)
    userFollowers = db.Column(db.Integer, unique=False, nullable=True)
    
    # One-to-many relationship: User to Blog (authored blogs)
    blogs = db.relationship('Blog', backref='author', lazy=True)
    
    # Many-to-many relationship: User to Blog (saved blogs)
    saved_blogs = db.relationship('Blog', secondary=saved_blogs, lazy='subquery',
                                  backref=db.backref('savers', lazy=True))
    
    role = db.Column(db.String(20), default='user')  # Default role is 'user'
    @hybrid_property
    def is_admin(self): 
        return self.role == 'admin'
    # userFollowers_id = 
    # repr method represents how one object of this datatable will look like
    def __repr__(self):
        return f"User({self.userName})"

# Create an admin view for the Product model
class UserAdminView(ModelView):
    form_extra_fields = {
        'userPNG': ImageUploadField('userPNG',
                                  base_path='static/userPNG',  # Where to store uploaded images
                                  thumbnail_size=(100, 100, True),  # Thumbnail size
                                  url_relative_path='userPNG/',  # Relative path to the images directory
                                  allowed_extensions=['jpg', 'jpeg', 'png'], # Allowed file extensions
                                  namegen=lambda field, original_filename: str(uuid.uuid4()))                             
    }
adminPanel.add_view(UserAdminView(User, db.session))


@addModel
class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50))
    page_visited = db.Column(db.String(150))
    method = db.Column(db.String(20))
    timestamp = db.Column(db.DateTime, default=datetime.now)
    
# Function to log the request
# @app.before_request
def log_request():
    ip_address = request.remote_addr
    page_visited = request.path
    method = request.method
    log = Log(ip_address=ip_address, page_visited=page_visited, method=method)
    db.session.add(log)
    db.session.commit()

@login_manager.user_loader
def loader_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        print("Error ", e)
        return
 
 
 
# function to add profiles
@app.route('/api/createUser', methods=["POST"])
def createUser():
    userName = request.form.get("user_name")
    userDescription = request.form.get("userDescription")
    userPNG = request.form.get("userPNG")
    userFollowers = 0

    # create an object of the Profile class of models
    # and store data as a row in our datatable
    if userName != '' and userDescription != '' and userPNG != '':
        p = User(userName=userName, userDescription=userDescription, userPNG=userPNG, userFollowers=userFollowers, email=f"{userName}@gmail.com", password=userName)
        db.session.add(p)
        db.session.commit()
        return jsonify({
            'OK':True
        })
    else:
        return jsonify({
            'OK':False
        })
@app.route('/api/deleteUser', methods=["POST"])
def deleteUser():
    #TODO delete all blog posts from the database
    id = request.form.get("id")
    user = User.query.get(id)
    if user:
        db.session.delete(user)
        db.session.commit()
        return jsonify({
            'OK':True
        })
    else:
        return jsonify({
            'OK':False
        })
@app.route('/api/listUser')
def allUser():
    print('\n\n\n\n')
    print(User.query.all())
    return jsonify({
            'users':[{
                        'id': i.id,
                        'userName' : i.userName,
                        'userDescription' : i.userDescription,
                        'userPNG' : i.userPNG,
                        'userFollowers': i.userFollowers
                    } for i in User.query.all()]
    })

@app.route('/api/post', methods=["POST"])
def post():
    jsndata = request.json
    user_id = jsndata.get("user_id")
    title = jsndata.get("title")
    data = jsndata.get("data")
    description = jsndata.get("description", None)
    tags = jsndata.get("tags", [])
    tags = [find_or_create_tag(i.strip()) for i in (tags if tags else [])]

    # create an object of the Profile class of models
    # and store data as a row in our datatable
    if user_id != None and title != '' and data != '':
        p = Blog(user_id=user_id, title=title, data=data, description=description, time_read=readingTime(data), tags=tags)
        db.session.add(p)
        db.session.commit()
        return jsonify({
            'OK':True
        })
    else:
        return jsonify({
            'OK':False
        })     
@app.route('/api/delete', methods=["POST"])
def erase():
    id = request.form.get("id")
    # Deletes the data on the basis of unique id
    data = Blog.query.get(id)
    if data:
        db.session.delete(data)
        db.session.commit()
        return jsonify({
            'OK':True
        })
    else:
        return jsonify({
            'OK':False
        })
@app.route('/api/list')
def sendAll():
    return jsonify({
            'blogs':[{
                        'id': i.id,
                        'user_id' : i.user_id,
                        'title' : i.title,
                        'description' : i.description,
                        'data' : i.data
                    } for i in Blog.query.all()]
    })
@app.route('/api/md2html', methods=["POST"])
def md2html():
    data = request.get_json()
    md = data.get('md')
    return jsonify({
        'html' : extract_markdown(md)
        })


# utility functions
def Trending(user=None):
    if PRODUCTION_VERSION:
        allBlogs = Blog.query.order_by(func.rand()).limit(6).all()
    else:
        allBlogs = Blog.query.order_by(func.random()).limit(6).all()
    
    theirUsers = [blog.author for blog in allBlogs]
    
    posts = [{'url': f'/{get_url(b.title, b.id, app.config["NOT_SECRET_KEY"])}',
              'idx': "{:02}".format(idx+1),
              'title': b.title,
              'date': f"{b.date_posted.strftime('%b %d, %Y')}",
              'length': f'{b.time_read} min',
              'author': 'Anonymous' if not u else u.userName,
              'author_url': '' if not u else f'/user/{get_url_by_name(u.userName)}',
              'author_img': 'None.png' if not u else u.userPNG} for (idx, (b, u)) in enumerate(zip(allBlogs, theirUsers))]
    if user is not None:    
        return posts[:3]
    else:
        return posts

def TrendingTags(user=None):
    if user is None:
        # sorted_tags = sorted([tag for tag in Tag.query.all()], key=lambda tag: len(tag.blogs), reverse=True)[:9]
        sorted_tags = Tag.query.options(joinedload(Tag.blogs)).limit(9).all()
        tags = [{
                'name':i.name,
                'url':get_url_by_name(i.name),
            } for i in sorted_tags]
        return tags
    else:
        sorted_tags = Tag.query.options(joinedload(Tag.blogs)).limit(9).all()
        tags = [{
                'name':i.name,
                'url':get_url_by_name(i.name),
            } for i in sorted_tags]
        return tags
def TrendingUsers(user=None):
    sorted_user = User.query.options(joinedload(User.blogs)).limit(3).all()
    return sorted_user

def get_posts(chunk_size=16, userid=None, allBlogs=None):
    """
    user = None => random blogs or tranding blog
    user = userid => get best blog using ai
    """
    if allBlogs is None:
        if PRODUCTION_VERSION:
            allBlogs = Blog.query.order_by(func.rand()).limit(chunk_size).all()
        else:
            allBlogs = Blog.query.order_by(func.random()).limit(chunk_size).all()
    theirUsers = [blog.author for blog in allBlogs]
    
    if userid is None:
        posts = [{'url': f'/{get_url(b.title, b.id, app.config["NOT_SECRET_KEY"])}',
                  'title': add_ellipsis(b.title),
                  'subtitle': add_ellipsis(b.description) if b.description else get_sub_title(b.data),
                  'img': get_img(b.data),
                  'tag': b.tags.limit(1).first().name if len(b.tags.all())>0 else None, #get_tags(b.data),
                  'tag_url': f'/tag/{get_url_by_name(b.tags.limit(1).first().name) if len(b.tags.all())>0 else None}',
                  'date': f"{b.date_posted.strftime('%b %d, %Y')}",
                  'length': f'{b.time_read} min',
                  'author': 'anonymous' if not u else u.userName,
                  'author_url': '' if not u else f'/user/{get_url_by_name(u.userName)}',
                  'author_img': 'None.png' if not u else u.userPNG} for b,u in zip(allBlogs, theirUsers)]
    else:
        posts = [{'url': f'/{get_url(b.title, b.id, app.config["NOT_SECRET_KEY"])}',
                  'title': add_ellipsis(b.title),
                  'subtitle': add_ellipsis(b.description) if b.description else get_sub_title(b.data),
                  'img': get_img(b.data),
                  'tag': b.tags.limit(1).first().name if len(b.tags.all())>0 else None, #get_tags(b.data),
                  'tag_url': f'/tag/{get_url_by_name(b.tags.limit(1).first().name) if len(b.tags.all())>0 else None}',
                  'date': f"{b.date_posted.strftime('%b %d, %Y')}",
                  'length': f'{b.time_read} min',
                  'author': 'anonymous' if not u else u.userName,
                  'author_url': '' if not u else f'/user/{get_url_by_name(u.userName)}',
                  'author_img': 'None.png' if not u else u.userPNG} for b,u in zip(allBlogs, theirUsers)]
    return posts
    
@app.route('/api/posts', methods=["POST"])
def more_posts():
    data = request.get_json()
    userid = data.get('userid')
    tag_id = data.get('tag_id')
    query = data.get('query')
    if tag_id:
        tag = Tag.query.get(tag_id)
        if tag is None: abort(404)
        allBlogs = tag.blogs
        return jsonify({
            'posts' : get_posts(userid=userid, chunk_size=24, allBlogs=allBlogs)
        })
    elif query:
        allBlogs = Blog.query.all()
        allBlogs = [b for b in allBlogs if query.lower() in b.title.lower()]
        return jsonify({
            'posts' : get_posts(userid=userid, chunk_size=24, allBlogs=allBlogs)
        })
    else:
        return jsonify({
            'posts' : get_posts(userid=userid, chunk_size=24)
        })



@app.route('/')
def home():
    log_request()
    keywords = 'Blogifyr, free blogging platform, diverse topics, community-driven, storytelling, articles, writers, readers, content discovery, online blogging, free content, digital publications, personal essays, opinion pieces, creative writing, technology, culture, lifestyle, education'
    if current_user.is_authenticated:
        return render_template('home.html', posts=get_posts(chunk_size=24, userid=current_user.id), 
                               trendingTags=TrendingTags(current_user), 
                               trendingUsers=TrendingUsers(current_user),
                               trending=Trending(current_user),
                               userid=current_user.id, user=current_user, keywords = keywords,
                               url=request.host, domain=urlparse(request.host).netloc) # , data='<div>'+''.join([f'<div><a href="/{i.id}">{i.title}</a></div>' for i in Blog.query.all()])+'</div>'
    else:
        return render_template('newUser.html', trending=Trending(), 
                               trendingTags=TrendingTags(), 
                               home_posts=get_posts(chunk_size=24), keywords = keywords,
                               url=request.host, domain=urlparse(request.host).netloc)

#TODO save password sha-256
@app.route('/login', methods=["GET", "POST"])
def login(): 
    if request.method == "POST":
        data = request.get_json()
        try:
            remember = True if data['remember'] else False
            user = User.query.filter_by(email=data['email']).limit(1).first()
            # if not user or not check_password_hash(user.password, password):
            if not user or not (user.password == data['otp']):
                return jsonify({
                    'ok': False,
                })
            else:
                login_user(user, remember=remember)
                return jsonify({
                    'ok': True,
                })
        except Exception as e:
            print("Error ", e)
            return jsonify({
                'ok': False,
            })
            
    return render_template('login.html')

@app.route('/signup', methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        data = request.get_json()
        try:
            user = User(userName=data['username'],
                     email=data['email'],
                     password=data['otp'])
            db.session.add(user)
            db.session.commit()
            return jsonify({
                'ok': True,
            })
        except Exception as e:
            print("Error ", e)
            return jsonify({
                'ok': False,
            })
    return render_template('signup.html')

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect('/')

@app.route('/new-story', methods=["GET", "POST"])
def write():
    log_request()
    if request.method == "POST":
        data = request.get_json()
        try:
            print(data)
            title = data['title']
            if title == '': raise ValueError("Empty title")
            tags = [find_or_create_tag(i.strip()) for i in data['tags'].split(',')]
            
            description = data['subtitle']
            p = Blog(user_id=current_user.id if current_user.is_authenticated else None, title=title, data=data['data'], description=description, time_read=readingTime(data['data']), tags=tags)
            db.session.add(p)
            db.session.commit()
            return jsonify({
                'OK':True
            }) 
        except Exception as e:
            print("Error ", e)
            return jsonify({
                'ok': False,
            })
    username, userimg, userid = (current_user.userName, current_user.userPNG, current_user.id) if current_user.is_authenticated else (None, None, None)
    return render_template('new-story.html', is_authenticated = current_user.is_authenticated, username = username, userimg = userimg, userid=userid)

@app.route('/user/', defaults={'username': None}, methods=["GET"])
@app.route('/user/<username>', methods=["GET"])
def profile(username):
    if username is None:
        if current_user.is_authenticated:
            return redirect(f'/user/{get_url_by_name(current_user.userName)}')
        else:
            return redirect('login')
    user = User.query.filter_by(userName=username.replace('_', '')).limit(1).first()
    if user is None: abort(404)
        
    keywords = 'Blogifyr, free blogging platform, diverse topics, community-driven, storytelling, articles, writers, readers, content discovery, online blogging, free content, digital publications, personal essays, opinion pieces, creative writing, technology, culture, lifestyle, education'
    return render_template('profile.html', posts=get_posts(chunk_size=24, userid=current_user.id if current_user.is_authenticated else None),
                               userid=current_user.id if current_user.is_authenticated else None, 
                               user=user, keywords = keywords,
                               url=request.host, domain=urlparse(request.host).netloc) # , data='<div>'+''.join([f'<div><a href="/{i.id}">{i.title}</a></div>' for i in Blog.query.all()])+'</div>'
    

@app.route('/tag/<id>', methods=["GET"])
def post_tag(id):
    name = id.replace('_', ' ')
    tag = Tag.query.filter_by(name=name).limit(1).first()
    if tag is None: abort(404)
    log_request()
    
    allBlogs = tag.blogs
    
    keywords = 'Blogifyr, free blogging platform, diverse topics, community-driven, storytelling, articles, writers, readers, content discovery, online blogging, free content, digital publications, personal essays, opinion pieces, creative writing, technology, culture, lifestyle, education'
    if current_user.is_authenticated:
        return render_template('home.html', posts=get_posts(chunk_size=24, userid=current_user.id, allBlogs=allBlogs), 
                               tag = tag,
                               trendingTags=TrendingTags(current_user), 
                               trendingUsers=TrendingUsers(current_user),
                               trending=Trending(current_user),
                               userid=current_user.id, user=current_user, keywords = keywords,
                               url=request.host, domain=urlparse(request.host).netloc) # , data='<div>'+''.join([f'<div><a href="/{i.id}">{i.title}</a></div>' for i in Blog.query.all()])+'</div>'
    else:
        return render_template('newUser.html',
                               tag = tag,
                               trendingTags=TrendingTags(), 
                               home_posts=get_posts(chunk_size=24, allBlogs=allBlogs), 
                               keywords = keywords,
                               url=request.host, domain=urlparse(request.host).netloc)

@login_required
@app.route('/api/save', methods=["POST"])
def save_post():
    # blog_to_save = Blog.query.first()
    # current_user.saved_blogs.append(blog_to_save)
    return f'SAVE NONE'
@app.route('/saved', methods=["GET"])
def save_posts():
    return f'SAVED'


@app.route('/search', methods=["GET"])
@login_required
def search_posts():
    query = request.args.get('query', None)
    if query:
        log_request()
        allBlogs = Blog.query.all()
        allBlogs = [b for b in allBlogs if query.lower() in b.title.lower()]
        keywords = 'Blogifyr, free blogging platform, diverse topics, community-driven, storytelling, articles, writers, readers, content discovery, online blogging, free content, digital publications, personal essays, opinion pieces, creative writing, technology, culture, lifestyle, education'
        return render_template('home.html', posts=get_posts(chunk_size=24, userid=current_user.id, allBlogs=allBlogs),
                               query = query,
                               trendingTags=TrendingTags(current_user), 
                               trendingUsers=TrendingUsers(current_user),
                               trending=Trending(current_user),
                               userid=current_user.id, user=current_user, keywords = keywords,
                               url=request.host, domain=urlparse(request.host).netloc)
    return redirect('/')



@app.route('/<id>')
def blogPage(id):
    log_request()
    if '-' not in id: abort(404)
    try: data = Blog.query.get(get_id(id, app.config["NOT_SECRET_KEY"]))
    except Exception as e: abort(404)
    if data and check_url(id, data, app.config["NOT_SECRET_KEY"]):
        user = data.author if data.user_id else None
        b = blog(user=user.userName if user else None,
            userPNG=user.userPNG if user else None,
            userFollowers=user.userFollowers if user else None,
            userDescription=user.userDescription if user else None,
            title=add_ellipsis(data.title),
            subtitle=add_ellipsis(data.description),
            post_date=f"{data.date_posted.strftime('%b %d, %Y')}",
            read_time=f'{data.time_read} min',
            reactions={
                'claps': data.claps,
                'Responds': '1'
            },
            tags=[tag.name for tag in data.tags])
        b.add(extract_markdown(data.data))
        
        return render_template('blog.html' if current_user.is_authenticated else 'blogNewUser.html', 
                               title=add_ellipsis(b.title),
                               headingHTML = b.getHeadingHTML(),
                               contentHTML = b.html, 
                               rootFooterHTML = b.getRootFooterHTML(),
                               data=b.html,
                               user=current_user,
                               author=data.author.userName if data.author else 'Anonymous',
                               img = get_img(data.data),
                               keywords = '',
                               description = add_ellipsis(data.description) or get_sub_title(data.data),
                               post_date=data.date_posted.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
                               url=request.host, domain=urlparse(request.host).netloc)
    else: 
        return "404 not found"



def resetDatabase():
    print("Database reset...")
    if PRODUCTION_VERSION == True:
        with app.app_context():
            db.reflect()
            db.drop_all()
            db.create_all()
            admin = User(email='admin', userName='ThefCraft', password='admin', role='admin')
            db.session.add(admin)
            db.session.commit()
    else:
        os.remove(os.path.join('database', os.listdir('database')[0]))
if RESET: resetDatabase()
if not PRODUCTION_VERSION and not os.path.exists(os.path.join(basedir, 'database\\database.db')):
    print('creating database ...')
    with app.app_context():
        db.create_all()
        
        # admin = User(email='', userName='admin', password=generate_password_hash('admin', method='scrypt'), role='admin')
        admin = User(email='admin', userName='ThefCraft', password='admin', role='admin')
        db.session.add(admin)
        db.session.commit()

if __name__ == '__main__':
    
    app.run(debug=DEBUG, host='0.0.0.0', port=5000)
