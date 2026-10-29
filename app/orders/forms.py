from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Length, Regexp, Optional


class CheckoutForm(FlaskForm):
    full_name = StringField('Họ và tên', validators=[DataRequired(), Length(max=100)])
    phone = StringField('Số điện thoại', validators=[
        DataRequired(),
        Regexp(r'^(0|\+84)\d{9,10}$', message='Số điện thoại không hợp lệ (vd: 0901234567).')])
    address = StringField('Địa chỉ nhận hàng', validators=[DataRequired(), Length(max=255)])
    note = TextAreaField('Ghi chú (tuỳ chọn)', validators=[Optional(), Length(max=255)])
    submit = SubmitField('Đặt hàng')
