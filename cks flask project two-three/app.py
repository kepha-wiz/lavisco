from flask import Flask, render_template, redirect, url_for, request, session, flash, make_response
from models import db, Candidate, Vote, Post, PollingStation, Agent, Voter
from io import BytesIO
from xhtml2pdf import pisa

app = Flask(__name__)
app.secret_key = 'your_secret_key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///election.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

@app.before_request
def create_tables():
    if not hasattr(app, 'tables_created'):
        db.create_all()
        app.tables_created = True

@app.route('/')
def index():
    return redirect(url_for('login'))

@app.route('/candidate/<int:candidate_id>/results')
def candidate_results(candidate_id):
    candidate = Candidate.query.get_or_404(candidate_id)

    results = (
        db.session.query(
            PollingStation.name,
            db.func.coalesce(db.func.sum(Vote.votes), 0).label('vote_count')
        )
        .outerjoin(
            Vote,
            (Vote.polling_station_id == PollingStation.id) & (Vote.candidate_id == candidate_id)
        )
        .group_by(PollingStation.id)
        .all()
    )

    return render_template('candidate_results.html', candidate=candidate, results=results)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        agent = Agent.query.filter_by(username=username, password=password).first()
        if agent:
            session['agent'] = username
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid login credentials')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'agent' not in session:
        return redirect(url_for('login'))
    return render_template('dashboard.html')

@app.route('/register_voter', methods=['GET', 'POST'])
def register_voter():
    if request.method == 'POST':
        voter_id = request.form['voter_id']
        name = request.form['name']
        new_voter = Voter(id=voter_id, name=name)  # Make sure id is set properly here
        db.session.add(new_voter)
        db.session.commit()
        flash('Voter registered successfully')
    return render_template('register_voter.html')

@app.route('/manage_posts', methods=['GET', 'POST'])
def manage_posts():
    if request.method == 'POST':
        post_name = request.form['post_name'].strip()

        # Check if a post with the same name already exists (case-insensitive)
        existing_post = Post.query.filter(db.func.lower(Post.name) == post_name.lower()).first()
        if existing_post:
            flash('A post with this name already exists.', 'error')
        else:
            new_post = Post(name=post_name)
            db.session.add(new_post)
            db.session.commit()
            flash('Post added successfully.', 'success')

    posts = Post.query.all()
    return render_template('manage_posts.html', posts=posts)
@app.route('/charts')
def charts():
    posts = Post.query.all()
    chart_data = []

    for post in posts:
        candidates = Candidate.query.filter_by(post_id=post.id).all()
        labels = []
        votes = []

        for candidate in candidates:
            total_votes = db.session.query(
                db.func.coalesce(db.func.sum(Vote.votes), 0)
            ).filter_by(candidate_id=candidate.id).scalar()

            labels.append(candidate.name)
            votes.append(total_votes)

        chart_data.append({
            'post': post.name,
            'labels': labels,
            'votes': votes
        })

    return render_template('charts.html', chart_data=chart_data)
@app.route('/delete_polling_station/<int:station_id>', methods=['POST'])
def delete_polling_station(station_id):
    station = PollingStation.query.get_or_404(station_id)
    db.session.delete(station)
    db.session.commit()
    flash('Polling station deleted successfully.')
    return redirect(url_for('manage_polling_stations'))

@app.route('/all_results')
def all_results():
    candidates = Candidate.query.all()

    results = []
    for candidate in candidates:
        # Skip candidates whose associated post is missing
        if not candidate.post:
            continue

        vote_data = (
            db.session.query(
                PollingStation.name,
                db.func.coalesce(db.func.sum(Vote.votes), 0)
            )
            .join(Vote, Vote.polling_station_id == PollingStation.id)
            .filter(Vote.candidate_id == candidate.id)
            .group_by(PollingStation.name)
            .all()
        )
        results.append({
            'candidate': candidate.name,
            'post': candidate.post.name,
            'votes': vote_data
        })

    return render_template('all_results.html', results=results)

@app.route('/register_candidate', methods=['GET', 'POST'])
def register_candidate():
    posts = Post.query.all()
    if request.method == 'POST':
        name = request.form['name'].strip()
        post_id = request.form['post']

        # Check for existing candidate with the same name (case-insensitive)
        existing_candidate = Candidate.query.filter(db.func.lower(Candidate.name) == name.lower()).first()
        if existing_candidate:
            flash('A candidate with this name already exists.', 'error')
        else:
            new_candidate = Candidate(name=name, post_id=post_id)
            db.session.add(new_candidate)
            db.session.commit()
            flash('Candidate registered successfully.', 'success')

    return render_template('register_candidate.html', posts=posts)
@app.route('/manage_polling_stations', methods=['GET', 'POST'])
def manage_polling_stations():
    if request.method == 'POST':
        station_name = request.form['station_name']
        if station_name.strip():  # simple validation
            new_station = PollingStation(name=station_name.strip())
            db.session.add(new_station)
            db.session.commit()
            flash('Polling station added successfully')
        else:
            flash('Please enter a valid name')
    stations = PollingStation.query.all()
    return render_template('manage_polling_stations.html', stations=stations)

@app.route('/enter_votes', methods=['GET', 'POST'])
def enter_votes():
    candidates = Candidate.query.all()
    stations = PollingStation.query.all()

    if request.method == 'POST':
        candidate_id_str = request.form.get('candidate', '')
        station_id_str = request.form.get('station', '')
        votes_str = request.form.get('votes', '')

        # Validate inputs
        if not candidate_id_str or not station_id_str or not votes_str:
            flash('Please fill in all fields.')
            return redirect(url_for('enter_votes'))

        try:
            candidate_id = int(candidate_id_str)
            station_id = int(station_id_str)
            vote_count = int(votes_str)
        except ValueError:
            flash('Invalid input: Candidate, Station, and Votes must be valid numbers.')
            return redirect(url_for('enter_votes'))

        if vote_count < 0:
            flash('Vote count cannot be negative.')
            return redirect(url_for('enter_votes'))

        existing_vote = Vote.query.filter_by(candidate_id=candidate_id, polling_station_id=station_id).first()
        if existing_vote:
            existing_vote.votes += vote_count
        else:
            new_vote = Vote(candidate_id=candidate_id, polling_station_id=station_id, votes=vote_count)
            db.session.add(new_vote)

        db.session.commit()
        flash('Votes entered successfully')
        return redirect(url_for('enter_votes'))

    return render_template('enter_votes.html', candidates=candidates, stations=stations)

@app.route('/delete_post/<int:post_id>', methods=['POST'])
def delete_post(post_id):
    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    flash('Post deleted successfully.')
    return redirect(url_for('manage_posts'))

@app.route('/results')
def results():
    results = (
        db.session.query(
            Candidate.name,
            db.func.coalesce(db.func.sum(Vote.votes), 0).label('vote_count')
        )
        .join(Vote)
        .group_by(Candidate.id)
        .order_by(db.desc('vote_count'))
        .all()
    )
    return render_template('results.html', results=results)

@app.route('/winners')
def winners():
    posts = Post.query.all()
    winners = []

    for post in posts:
        top_candidate = (
            db.session.query(
                Candidate.name,
                db.func.coalesce(db.func.sum(Vote.votes), 0).label('vote_count')
            )
            .join(Vote)
            .filter(Candidate.post_id == post.id)
            .group_by(Candidate.id)
            .order_by(db.desc('vote_count'))
            .first()
        )
        if top_candidate:
            winners.append({'post': post.name, 'candidate': top_candidate.name, 'votes': top_candidate.vote_count})

    return render_template('winners.html', winners=winners)

@app.route('/export_pdf')
def export_pdf():
    posts = Post.query.all()
    winners = []

    for post in posts:
        top_candidate = (
            db.session.query(
                Candidate.name,
                db.func.coalesce(db.func.sum(Vote.votes), 0).label('vote_count')
            )
            .join(Vote)
            .filter(Candidate.post_id == post.id)
            .group_by(Candidate.id)
            .order_by(db.desc('vote_count'))
            .first()
        )
        if top_candidate:
            winners.append({'post': post.name, 'candidate': top_candidate.name, 'votes': top_candidate.vote_count})

    html = render_template('pdf_template.html', winners=winners)
    result = BytesIO()
    pisa_status = pisa.CreatePDF(html, dest=result)

    if pisa_status.err:
        return "Error generating PDF", 500

    response = make_response(result.getvalue())
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = 'attachment; filename=winners.pdf'
    return response

if __name__ == '__main__':
    app.run(debug=True)
