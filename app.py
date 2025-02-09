from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy.dialects.postgresql import JSON
from dotenv import load_dotenv
import os
from sqlalchemy import text, extract
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity
from werkzeug.security import generate_password_hash, check_password_hash
from flasgger import Swagger, swag_from
import logging
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'super-secret-key')


db = SQLAlchemy(app)
jwt = JWTManager(app)
swagger = Swagger(app)


logging.basicConfig(level=logging.INFO)


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username
        }

class Classe(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nome = db.Column(db.String(255), unique=True, nullable=False)
    professor = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'professor': self.professor
        }

class Aluno(db.Model):
    __tablename__ = 'alunos'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nome = db.Column(db.String(255), nullable=False)
    data_nascimento = db.Column(db.Date, nullable=False)
    status = db.Column(db.Enum('MATRICULADO', 'DESMATRICULADO', name='status_aluno'),
                       default='MATRICULADO')
    classe_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nome': self.nome,
            'data_nascimento': self.data_nascimento.strftime('%Y-%m-%d'),
            'status': self.status,
            'classe_id': self.classe_id
        }

class Frequencia(db.Model):
    __tablename__ = 'frequencias'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    classe_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    data = db.Column(db.Date, nullable=False)
    total_biblia = db.Column(db.Integer, default=0)
    total_present = db.Column(db.Integer, default=0)
    total_absent = db.Column(db.Integer, default=0)
    total_visitors = db.Column(db.Integer, default=0)
    total_general = db.Column(db.Integer, default=0)
    presencas = db.Column(JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'classe_id': self.classe_id,
            'data': self.data.strftime('%Y-%m-%d'),
            'total_biblia': self.total_biblia,
            'total_present': self.total_present,
            'total_absent': self.total_absent,
            'total_visitors': self.total_visitors,
            'total_general': self.total_general,
            'presencas': self.presencas
        }


with app.app_context():
    with db.engine.connect() as connection:
        connection.execute(text("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_type WHERE typname = 'status_aluno'
                ) THEN
                    CREATE TYPE status_aluno AS ENUM ('MATRICULADO', 'DESMATRICULADO');
                END IF;
            END $$;
        """))
    db.create_all()



@app.route('/register', methods=['POST'])
@swag_from({
    'responses': {
        201: {
            'description': 'Usuário registrado',
            'schema': {
                'type': 'object',
                'properties': {
                    'id': {'type': 'integer'},
                    'username': {'type': 'string'}
                }
            }
        }
    }
})
def register():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'msg': 'Username e password são obrigatórios'}), 400
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'msg': 'Username já existe'}), 400
    user = User(username=data['username'])
    user.set_password(data['password'])
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201

@app.route('/login', methods=['POST'])
@swag_from({
    'responses': {
        200: {
            'description': 'Usuário autenticado, token retornado',
            'schema': {
                'type': 'object',
                'properties': {
                    'access_token': {'type': 'string'}
                }
            }
        }
    }
})
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'msg': 'Username e password são obrigatórios'}), 400
    user = User.query.filter_by(username=data['username']).first()
    if user and user.check_password(data['password']):
        token = create_access_token(identity=user.id, expires_delta=timedelta(hours=1))
        return jsonify({'access_token': token}), 200
    return jsonify({'msg': 'Credenciais inválidas'}), 401

@app.route('/protected', methods=['GET'])
@jwt_required()
def protected():
    current_user = get_jwt_identity()
    return jsonify({'msg': f'Usuário logado: {current_user}'}), 200



@app.route('/classes', methods=['GET'])
@jwt_required()
def listar_classes():
    classes = Classe.query.all()
    return jsonify([classe.to_dict() for classe in classes]), 200

@app.route('/classes', methods=['POST'])
@jwt_required()
def criar_classe():
    data = request.get_json()
    if not data or not data.get('nome') or not data.get('professor'):
        return jsonify({'msg': 'Campos "nome" e "professor" são obrigatórios'}), 400
    nova_classe = Classe(nome=data['nome'], professor=data['professor'])
    db.session.add(nova_classe)
    db.session.commit()
    return jsonify(nova_classe.to_dict()), 201

@app.route('/classes/<int:classe_id>', methods=['PUT'])
@jwt_required()
def atualizar_classe(classe_id):
    data = request.get_json()
    classe = Classe.query.get_or_404(classe_id)
    if 'nome' in data:
        classe.nome = data['nome']
    if 'professor' in data:
        classe.professor = data['professor']
    db.session.commit()
    return jsonify(classe.to_dict()), 200

@app.route('/classes/<int:classe_id>', methods=['DELETE'])
@jwt_required()
def deletar_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)
    db.session.delete(classe)
    db.session.commit()
    return jsonify({'msg': 'Classe deletada'}), 200



@app.route('/alunos', methods=['GET'])
@jwt_required()
def listar_alunos():
    alunos = Aluno.query.all()
    return jsonify([aluno.to_dict() for aluno in alunos]), 200

@app.route('/alunos', methods=['POST'])
@jwt_required()
def criar_aluno():
    data = request.get_json()
    required_fields = ['nome', 'data_nascimento', 'classe_id']
    if not all(field in data for field in required_fields):
        return jsonify({'msg': 'Campos obrigatórios ausentes'}), 400
    try:
        novo_aluno = Aluno(
            nome=data['nome'],
            data_nascimento=datetime.strptime(data['data_nascimento'], '%Y-%m-%d'),
            classe_id=data['classe_id']
        )
    except Exception as e:
        return jsonify({'msg': 'Formato de data inválido', 'error': str(e)}), 400
    db.session.add(novo_aluno)
    db.session.commit()
    return jsonify(novo_aluno.to_dict()), 201

@app.route('/alunos/<int:aluno_id>', methods=['PUT'])
@jwt_required()
def atualizar_aluno(aluno_id):
    data = request.get_json()
    aluno = Aluno.query.get_or_404(aluno_id)
    if 'nome' in data:
        aluno.nome = data['nome']
    if 'data_nascimento' in data:
        try:
            aluno.data_nascimento = datetime.strptime(data['data_nascimento'], '%Y-%m-%d')
        except Exception as e:
            return jsonify({'msg': 'Formato de data inválido', 'error': str(e)}), 400
    if 'classe_id' in data:
        aluno.classe_id = data['classe_id']
    if 'status' in data:
        aluno.status = data['status']
    db.session.commit()
    return jsonify(aluno.to_dict()), 200

@app.route('/alunos/<int:aluno_id>', methods=['DELETE'])
@jwt_required()
def deletar_aluno(aluno_id):
    aluno = Aluno.query.get_or_404(aluno_id)
    db.session.delete(aluno)
    db.session.commit()
    return jsonify({'msg': 'Aluno deletado'}), 200



@app.route('/frequencias', methods=['GET'])
@jwt_required()
def listar_frequencias():
    frequencias = Frequencia.query.all()
    return jsonify([frequencia.to_dict() for frequencia in frequencias]), 200

@app.route('/frequencias', methods=['POST'])
@jwt_required()
def registrar_frequencia():
    data = request.get_json()
    required_fields = ['classe_id', 'data']
    if not all(field in data for field in required_fields):
        return jsonify({'msg': 'Campos "classe_id" e "data" são obrigatórios'}), 400
    try:
        nova_frequencia = Frequencia(
            classe_id=data['classe_id'],
            data=datetime.strptime(data['data'], '%Y-%m-%d'),
            total_biblia=data.get('total_biblia', 0),
            total_present=data.get('total_present', 0),
            total_absent=data.get('total_absent', 0),
            total_visitors=data.get('total_visitors', 0),
            total_general=data.get('total_general', 0),
            presencas=data.get('presencas', [])
        )
    except Exception as e:
        return jsonify({'msg': 'Formato de data inválido', 'error': str(e)}), 400
    db.session.add(nova_frequencia)
    db.session.commit()
    return jsonify(nova_frequencia.to_dict()), 201

@app.route('/frequencias/<int:frequencia_id>', methods=['PUT'])
@jwt_required()
def atualizar_frequencia(frequencia_id):
    data = request.get_json()
    frequencia = Frequencia.query.get_or_404(frequencia_id)
    if 'classe_id' in data:
        frequencia.classe_id = data['classe_id']
    if 'data' in data:
        try:
            frequencia.data = datetime.strptime(data['data'], '%Y-%m-%d')
        except Exception as e:
            return jsonify({'msg': 'Formato de data inválido', 'error': str(e)}), 400
    if 'total_biblia' in data:
        frequencia.total_biblia = data['total_biblia']
    if 'total_present' in data:
        frequencia.total_present = data['total_present']
    if 'total_absent' in data:
        frequencia.total_absent = data['total_absent']
    if 'total_visitors' in data:
        frequencia.total_visitors = data['total_visitors']
    if 'total_general' in data:
        frequencia.total_general = data['total_general']
    if 'presencas' in data:
        frequencia.presencas = data['presencas']
    db.session.commit()
    return jsonify(frequencia.to_dict()), 200

@app.route('/frequencias/<int:frequencia_id>', methods=['DELETE'])
@jwt_required()
def deletar_frequencia(frequencia_id):
    frequencia = Frequencia.query.get_or_404(frequencia_id)
    db.session.delete(frequencia)
    db.session.commit()
    return jsonify({'msg': 'Frequência deletada'}), 200



@app.route('/relatorios/semanal', methods=['GET'])
@jwt_required()
def relatorio_semanal():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    try:
        start_date = datetime.strptime(data_inicio, '%Y-%m-%d')
        end_date = datetime.strptime(data_fim, '%Y-%m-%d')
    except Exception as e:
        return jsonify({'msg': 'Formato de data inválido', 'error': str(e)}), 400
    frequencias = Frequencia.query.filter(Frequencia.data.between(start_date, end_date)).all()
    return jsonify([frequencia.to_dict() for frequencia in frequencias]), 200

@app.route('/relatorios/mensal', methods=['GET'])
@jwt_required()
def relatorio_mensal():
    mes = request.args.get('mes')
    ano = request.args.get('ano')
    if not mes or not ano:
        return jsonify({'msg': 'Parâmetros "mes" e "ano" são obrigatórios'}), 400
    frequencias = Frequencia.query.filter(
        extract('month', Frequencia.data) == int(mes),
        extract('year', Frequencia.data) == int(ano)
    ).all()
    return jsonify([frequencia.to_dict() for frequencia in frequencias]), 200



@app.route('/aniversariantes', methods=['GET'])
@jwt_required()
def listar_aniversariantes():
    hoje = datetime.utcnow()
    alunos = Aluno.query.filter(
        extract('month', Aluno.data_nascimento) == hoje.month,
        extract('day', Aluno.data_nascimento) == hoje.day
    ).all()
    return jsonify([aluno.to_dict() for aluno in alunos]), 200

@app.route('/alunos/<int:aluno_id>/historico', methods=['GET'])
@jwt_required()
def historico_frequencia(aluno_id):
    historico = []
    frequencias = Frequencia.query.all()
    for freq in frequencias:
        if freq.presencas and isinstance(freq.presencas, list):
            for presenca in freq.presencas:
                if presenca.get('aluno_id') == aluno_id:
                    record = freq.to_dict()
                    record['presenca'] = presenca  
                    historico.append(record)
                    break
    return jsonify(historico), 200


@app.route('/')
def hello():
    return "Sistema de Gestão da EBD - API com melhorias (Autenticação, CRUD, Validações e Documentação)"


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
