from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import (StringField, TextAreaField, IntegerField, SelectField,
                     BooleanField, SubmitField)
from wtforms.validators import DataRequired, Length, NumberRange, Optional

from app.models import ORDER_STATUSES


class ProductForm(FlaskForm):
    name = StringField('Tên sản phẩm', validators=[DataRequired(), Length(max=150)])
    category = SelectField('Danh mục', coerce=int)
    price = IntegerField('Giá (VND)', validators=[
        DataRequired('Vui lòng nhập giá.'), NumberRange(min=0, message='Giá không được âm.')])
    stock = IntegerField('Tồn kho', validators=[
        NumberRange(min=0, message='Tồn kho không được âm.')], default=0)
    description = TextAreaField('Mô tả', validators=[Optional()])
    image = FileField('Ảnh sản phẩm', validators=[
        FileAllowed(['jpg', 'jpeg', 'png', 'webp', 'gif'], 'Chỉ nhận ảnh jpg, png, webp, gif.')])
    is_active = BooleanField('Đang bán (hiển thị trên cửa hàng)', default=True)
    submit = SubmitField('Lưu')


class CategoryForm(FlaskForm):
    name = StringField('Tên danh mục', validators=[DataRequired(), Length(max=80)])
    submit = SubmitField('Thêm danh mục')


class OrderStatusForm(FlaskForm):
    status = SelectField('Trạng thái', choices=[(k, v[0]) for k, v in ORDER_STATUSES.items()])
    submit = SubmitField('Cập nhật')
