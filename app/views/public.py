# -*- coding: utf-8 -*-
"""
    public.py
    ~~~~~~~~~~~~~~

    Public pages/actions.

    :copyright: (c) 2016 by fengweimin.
    :date: 16/5/12
"""

from flask import Blueprint, render_template, current_app, session, redirect, request, jsonify
from flask_babel import gettext as _
from flask_login import login_user, logout_user, login_required
from flask_principal import identity_changed, Identity, AnonymousIdentity
from flask_wtf import Form
from werkzeug.security import check_password_hash, generate_password_hash
from wtforms import StringField, PasswordField, BooleanField, HiddenField
from wtforms.validators import DataRequired, Email

from app.models import User
from app.models import Price
from app.tools import send_support_email
import pymongo
# -------------------------------------------------------
from app.models import Post, Tag, User
from app.mongosupport import Pagination, populate_model
import datetime
import app.okexapi.OkcoinSpotAPI as okex
import time
import requests

# -------------------------------------------------------
public = Blueprint('public', __name__)

# Query OKEX api
apikey = None
secretkey = None
okcoinRESTURL = 'www.okcoin.com'
# 现货API
okcoinSpot = okex.OKCoinSpot(okcoinRESTURL, apikey, secretkey)
bitfinexUrl = "https://api.bitfinex.com/v2/candles/"


# @public.route('/click', methods=["GET"])
def okex_price_new():
    added = okex_global_price_new(current_app._get_current_object())
    return jsonify(success=True, prices=added, message='Success')


def okex_global_price_new(app):
    code = 'btc_usd'
    cursor = okcoinSpot.kline(code, '12hour')
    added = []
    for c in cursor:
        existing = Price.find_one({'date': unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c[0] / 1000)))})
        if not existing:
            price = Price()
            price.date = unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c[0] / 1000)))
            price.code = unicode(code)
            price.open = float(c[1])
            price.highest = float(c[2])
            price.lowest = float(c[3])
            price.close = float(c[4])
            price.createTime = datetime.datetime.now()
            price.save()

            added.append(price)
            app.logger.info('Saved %s' % price)
        else:
            app.logger.info(
                'Skipped %s' % unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c[0] / 1000))))
    return added


@public.route('/click', methods=["GET"])
def bitfinex_price_new():
    added = bitfinex_global_price_new(current_app._get_current_object())
    return jsonify(success=True, prices=added, message='Success')


def bitfinex_global_price_new(app):
    TimeFrame = 'trade:' + '12h' + ':'
    code = 'tBTCUSD'
    Section = '/hist'  # /hist 或者 /last
    url = bitfinexUrl + TimeFrame + code + Section
    # 由于返回值是字符串，因此需要对数据进行操作
    response = requests.request("GET", url)
    text = response.content[1:-1]
    text = text.replace('[', '')
    text = text.replace(']', '')
    res = text.split(',')

    # print(res)
    cursor = []
    count = 0
    for r in res:
        if count == 6:
            cursor.append(tmp)
            count = 0
        if count == 0:
            tmp = [float(r)]
        else:
            tmp.append(float(r))
        count += 1

    app.logger.info('cursor:\n{0}'.format(cursor))
    added = []
    for c in cursor:
        existing = Price.find_one({'date': unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c[0] / 1000)))})
        if not existing:
            price = Price()
            price.date = unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c[0] / 1000)))
            price.code = unicode(code)
            price.open = float(c[1])
            price.highest = float(c[3])
            price.lowest = float(c[4])
            price.close = float(c[2])
            price.createTime = datetime.datetime.now()
            price.save()

            added.append(price)
            app.logger.info('Saved %s' % price)
        else:
            app.logger.info(
                'Skipped %s' % unicode(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(c[0] / 1000))))
    return added


@public.route('/')
def index():
    """
    Index page.
    """
    cursor = Price.find({}, sort=[('date', pymongo.ASCENDING)])
    prices = [[c.date, c.open, c.close, c.lowest, c.highest] for c in cursor]
    current_app.logger.info('Found %s prices' % len(prices))
    return render_template('public/index.html', prices=prices)


@public.route('/blank')
def blank():
    """
    Blank page.
    """
    return render_template('public/blank.html')


@public.route('/styleguide')
def styleguide():
    """
    Blank page.
    """
    return render_template('public/styleguide.html')


# ----------------------------------------------------------------------------------------------------------------------
# Login/Signup
#

class LoginForm(Form):
    email = StringField('email', validators=[DataRequired(), Email()])
    password = PasswordField('password', validators=[DataRequired()])
    remember = BooleanField('remember')
    next_url = HiddenField('next')


@public.route('/login', methods=('GET', 'POST'))
def login():
    """
    Login.
    """
    form = LoginForm()

    if form.validate_on_submit():
        em = form.email.data.strip().lower()
        u = User.find_one({'email': em})
        if not u or not check_password_hash(u.password, form.password.data):
            return render_template('public/login.html', form=form, error=_('User name or password incorrect!'))

        # Keep the user info in the session using Flask-Login
        login_user(u)

        # Tell Flask-Principal the identity changed
        identity_changed.send(current_app._get_current_object(), identity=Identity(u.get_id()))

        next_url = form.next_url.data
        if not next_url:
            next_url = '/'
        return redirect(next_url)

    next_url = request.args.get('next', '')
    form.next_url.data = next_url
    return render_template('public/login.html', form=form)


@public.route('/logout')
@login_required
def logout():
    """
    Logout.
    """
    logout_user()

    # Remove session keys set by Flask-Principal
    for key in ('identity.name', 'identity.auth_type'):
        session.pop(key, None)

    # Tell Flask-Principal the user is anonymous
    identity_changed.send(current_app._get_current_object(), identity=AnonymousIdentity())

    return redirect("/")


class SignupForm(Form):
    email = StringField('email', validators=[DataRequired(), Email()])
    password = PasswordField('password', validators=[DataRequired()])
    repassword = PasswordField('repassword', validators=[DataRequired()])
    agree = BooleanField('agree', validators=[DataRequired(_('Please agree our service policy!'))])


@public.route('/signup', methods=('GET', 'POST'))
def signup():
    """
    Signup.
    """
    form = SignupForm()

    if form.validate_on_submit():
        if not form.password.data == form.repassword.data:
            return render_template('public/signup.html', form=form, error=_('Password dismatch!'))

        em = form.email.data.strip().lower()
        u = User.find_one({'email': em})
        if u:
            return render_template('public/signup.html', form=form, error=_('This email has been registered!'))

        u = User()
        u.email = em
        u.password = unicode(generate_password_hash(form.password.data.strip()))
        u.name = u.email.split('@')[0]
        u.save()

        current_app.logger.info('A new user created, %s' % u)
        send_support_email('signup()', u'New user %s with id %s.' % (u.email, u._id))

        # Keep the user info in the session using Flask-Login
        login_user(u)

        # Tell Flask-Principal the identity changed
        identity_changed.send(current_app._get_current_object(), identity=Identity(u.get_id()))

        return redirect('/')

    return render_template('public/signup.html', form=form)
