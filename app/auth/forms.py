import sqlalchemy as sa
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app import db
from app.models import User


class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Mật khẩu', validators=[DataRequired()])
    remember_me = BooleanField('Ghi nhớ đăng nhập')
    submit = SubmitField('Đăng nhập')


class RegisterForm(FlaskForm):
    username = StringField('Tên hiển thị', validators=[DataRequired(), Length(2, 64)])
    email = StringField('Email', validators=[DataRequired(), Email(), Length(max=120)])
    password = PasswordField('Mật khẩu', validators=[DataRequired(), Length(min=6)])
    password2 = PasswordField('Nhập lại mật khẩu',
                              validators=[DataRequired(), EqualTo('password', 'Mật khẩu không khớp.')])
    submit = SubmitField('Đăng ký')

    def validate_username(self, field):
        if db.session.scalar(sa.select(User).where(User.username == field.data)):
            raise ValidationError('Tên này đã được sử dụng.')

    def validate_email(self, field):
        if db.session.scalar(sa.select(User).where(User.email == field.data.lower())):
            raise ValidationError('Email này đã được đăng ký.')
