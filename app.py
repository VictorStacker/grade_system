from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import pandas as pd
import datetime
from sqlalchemy.exc import SQLAlchemyError

# 初始化 Flask 应用
app = Flask(__name__)

# 配置数据库，这里使用 SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///exam_data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 设置一个密钥，用于会话和flash消息
app.secret_key = 'your_secret_key'

# 初始化 SQLAlchemy，用于数据库操作
db = SQLAlchemy(app)


class CandidateInfo(db.Model):
    __tablename__ = 'candidate_info'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    gender = db.Column(db.String(20), nullable=False)
    id_type = db.Column(db.String(50), nullable=False)
    id_number = db.Column(db.String(80), nullable=False, unique=True)
    pinyin = db.Column(db.String(80), nullable=False)
    birthday = db.Column(db.Date, nullable=False)
    institution = db.Column(db.String(100), nullable=False)
    teacher = db.Column(db.String(80), nullable=False)
    exam_results = db.relationship('ExamResult', backref='candidate', lazy=True)


class ExamLocation(db.Model):
    __tablename__ = 'exam_location'
    id = db.Column(db.Integer, primary_key=True)
    location = db.Column(db.String(100), nullable=False)
    exam_date = db.Column(db.Date, nullable=False)
    exams = db.relationship('ExamResult', backref='exam_location', lazy=True)


class ExamResult(db.Model):
    __tablename__ = 'exam_result'
    id = db.Column(db.Integer, primary_key=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey('candidate_info.id', ondelete='CASCADE'), nullable=False)
    exam_level = db.Column(db.Integer, nullable=False)
    location_id = db.Column(db.Integer, db.ForeignKey('exam_location.id', ondelete='CASCADE'), nullable=False)
    passed = db.Column(db.Boolean, nullable=False)


# 辅助函数定义
def process_candidate_info(name, gender, id_type, id_number, pinyin, birthday_str, institution, teacher,
                           exam_level_str):
    try:
        exam_level = int(exam_level_str)
        birthday = datetime.datetime.strptime(birthday_str, '%Y-%m-%d').date() if birthday_str else None

        # 检查考生是否已存在
        existing_candidate = CandidateInfo.query.filter_by(id_number=id_number).first()

        if existing_candidate:
            # 考生已存在，检查考试等级
            return handle_existing_candidate(existing_candidate, exam_level)
        else:
            # 考生不存在，只能报名第一级
            if exam_level != 1:
                flash('新考生只能报名第一级考试。', 'warning')
                return False
            return add_new_candidate(name, gender, id_type, id_number, pinyin, birthday, institution, teacher, exam_level)
    except SQLAlchemyError as e:
        flash('数据库错误: ' + str(e), 'error')
        return False


def handle_existing_candidate(candidate, exam_level):
    try:
        # 检查是否已通过当前级别
        current_level_passed = ExamResult.query.filter_by(
            candidate_id=candidate.id, exam_level=exam_level, passed=True
        ).first()
        if current_level_passed:
            flash(f'已通过第{exam_level}级考试，不能重复报名。', 'warning')
            return False

        # 检查是否已通过前一级（如果报名的不是第一级）
        if exam_level > 1:
            previous_level_passed = ExamResult.query.filter_by(
                candidate_id=candidate.id, exam_level=exam_level - 1, passed=True
            ).first()
            if not previous_level_passed:
                flash(f'未通过第{exam_level - 1}级考试，不能报名第{exam_level}级。', 'warning')
                return False

        # 添加新的考级信息
        new_exam_result = ExamResult(
            candidate_id=candidate.id,
            exam_level=exam_level,
            passed=False  # 默认设置为未通过，考试结果需要另行录入
        )
        db.session.add(new_exam_result)
        db.session.commit()
        flash(f'考生已成功报名第{exam_level}级考试。')
        return True
    except SQLAlchemyError as e:
        flash('数据库错误: ' + str(e), 'error')
        return False


def add_new_candidate(name, gender, id_type, id_number, pinyin, birthday, institution, level, teacher):
    try:
        # 处理新考生的情况
        if level != 1:
            flash('新考生只能报名第一级考试。', 'warning')
            return

        # 创建新的考生信息
        new_candidate = CandidateInfo(
            name=name,
            gender=gender,
            id_type=id_type,
            id_number=id_number,
            pinyin=pinyin,
            birthday=birthday,
            institution=institution,
            teacher=teacher
        )
        db.session.add(new_candidate)
        db.session.commit()
    except SQLAlchemyError as e:
        flash('数据库错误: ' + str(e), 'error')
        return False


# 主页路由
@app.route('/')
def index():
    return render_template('index.html')


# 处理来自表单的单个考生信息的提交
@app.route('/add_candidate', methods=['GET', 'POST'])
def add_candidate():
    if request.method == 'POST':
        # 处理表单提交
        success = process_candidate_info(
            request.form['name'], request.form['gender'], request.form['id_type'],
            request.form['id_number'], request.form['pinyin'], request.form['birthday'],
            request.form['institution'], request.form['teacher'], request.form['registration_level']
        )
        if success:
            flash('考生信息已成功录入！')
        return redirect(url_for('add_candidate'))

    return render_template('add_candidate.html')


# 处理批量上传文件的请求
@app.route('/upload_candidate_info', methods=['POST'])
def upload_candidate_info():
    if 'file' in request.files:
        file = request.files['file']
        if file and allowed_file(file.filename):
            df = pd.read_excel(file)
            for index, row in df.iterrows():
                process_candidate_info(
                    row['name'], row['gender'], row['id_type'],
                    row['id_number'], row['pinyin'], row['birthday'],
                    row['institution'], row['teacher'], row['registration_level']
                )
            flash('批量考生信息已成功录入！')
        else:
            flash('未上传文件或文件格式不正确，请重试。', 'error')
    else:
        flash('没有文件部分')
    return redirect(url_for('add_candidate'))


# 录入考级结果的路由
@app.route('/add_exam_result', methods=['GET', 'POST'])
def add_exam_result():
    if request.method == 'POST':
        id_number = request.form['id_number']
        exam_level = int(request.form['level'])
        exam_date = datetime.datetime.strptime(request.form['exam_date'], '%Y-%m-%d').date()
        exam_location = request.form['exam_location']
        passed = request.form.get('passed') == 'True'

        # 根据身份证号查找考生信息
        candidate = CandidateInfo.query.filter_by(id_number=id_number).first()
        if candidate:
            # 创建新的考级结果
            new_result = ExamResult(candidate_id=candidate.id, exam_level=exam_level,
                                    exam_date=exam_date, exam_location=exam_location,
                                    passed=passed)
            db.session.add(new_result)
            db.session.commit()
            flash('考级结果已成功录入！')
        else:
            flash('找不到对应的考生信息。')

    return render_template('add_exam_result.html')


@app.route('/get_candidate_info/<id_number>', methods=['GET', 'POST'])
def get_candidate_info(id_number):
    # 联合查询考生信息和考级结果
    candidate = CandidateInfo.query.filter_by(id_number=id_number).first()
    if candidate:
        latest_result = ExamResult.query.filter_by(candidate_id=candidate.id).order_by(
            ExamResult.exam_date.desc()).first()
        response_data = {
            'name': candidate.name,
            'id_number': candidate.id_number,
            'exam_level': latest_result.exam_level if latest_result else None,
            'exam_date': latest_result.exam_date.strftime("%Y-%m-%d") if latest_result else None,
            'exam_location': latest_result.exam_location if latest_result else None,
            'passed': latest_result.passed if latest_result else None
        }
        return jsonify(response_data)
    return jsonify({'error': '未找到考生信息'})


# 查询考级资料的路由
@app.route('/search', methods=['GET'])
def search():
    search_query = request.args.get('search_query')
    if search_query:
        # 获取考生的所有考试记录
        results = ExamResult.query.join(CandidateInfo).filter(
            (CandidateInfo.name == search_query) | (CandidateInfo.id_number == search_query)).order_by(
            ExamResult.exam_date.desc()).all()
    else:
        results = []
    return render_template('search.html', results=results)


# 修改考生信息的路由
@app.route('/edit_candidate/<int:id>', methods=['GET', 'POST'])
def edit_candidate(id):
    candidate = CandidateInfo.query.get_or_404(id)
    if request.method == 'POST':
        candidate.name = request.form['name']
        candidate.gender = request.form['gender']
        candidate.id_type = request.form['id_type']
        candidate.id_number = request.form['id_number']
        candidate.pinyin = request.form['pinyin']
        candidate.birthday = datetime.datetime.strptime(request.form['birthday'], '%Y-%m-%d').date() if request.form[
            'birthday'] else None
        candidate.institution = request.form['institution']
        db.session.commit()
        flash('考生信息已成功更新！')
        return redirect(url_for('search'))
    return render_template('edit_candidate.html', candidate=candidate)


# 修改考级结果的路由
@app.route('/edit_exam_result/<int:id>', methods=['GET', 'POST'])
def edit_exam_result(id):
    exam_result = ExamResult.query.get_or_404(id)
    if request.method == 'POST':
        exam_result.exam_level = int(request.form['exam_level'])
        exam_result.exam_date = datetime.datetime.strptime(request.form['exam_date'], '%Y-%m-%d').date()
        exam_result.exam_location = request.form['exam_location']
        exam_result.passed = request.form.get('passed') == 'True'
        db.session.commit()
        flash('考级结果已成功更新！')
        return redirect(url_for('search'))
    return render_template('edit_exam_result.html', exam_result=exam_result)


# 删除考生信息的路由
@app.route('/delete_candidate/<int:id>', methods=['POST'])
def delete_candidate(id):
    candidate = CandidateInfo.query.get_or_404(id)
    db.session.delete(candidate)
    db.session.commit()
    flash('考生信息已成功删除！')
    return redirect(url_for('search'))


# 删除考级结果的路由
@app.route('/delete_exam_result/<int:id>', methods=['POST'])
def delete_exam_result(id):
    exam_result = ExamResult.query.get_or_404(id)
    db.session.delete(exam_result)
    db.session.commit()
    flash('考级结果已成功删除！')
    return redirect(url_for('search'))


@app.route('/modify')
def modify():
    # 获取所有考生和考级结果的记录
    candidates = CandidateInfo.query.all()
    exam_results = ExamResult.query.all()
    return render_template('modify.html', candidates=candidates, exam_results=exam_results)


# 应用启动入口
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 在应用启动时创建数据库表
    app.run(debug=True)
