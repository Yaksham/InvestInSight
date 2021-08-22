import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from time import localtime, strftime
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_stocks = db.execute("SELECT symbol, amount FROM stocks WHERE user_id=?", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
    current_price = {}
    for row in user_stocks:
        current_price[row['symbol']] = lookup(row['symbol'])['price']
    return render_template("index.html", user_stocks=user_stocks, cash=cash, current_price=current_price)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "GET":
        return render_template("buy.html", symbol=request.args.get("symbol", ""))
    else:
        if not lookup(request.form.get("symbol")):
            return apology("Invalid Symbol", 400)
        if not request.form.get("shares").isdigit():
            return apology("Invalid amount", 400)
        cost = int(request.form.get("shares")) * lookup(request.form.get("symbol"))["price"]
        cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
        if cost and cost <= cash:
            db.execute("INSERT INTO stocks (user_id, symbol, amount) VALUES(?, ?, ?) ON CONFLICT(user_id, symbol) DO UPDATE SET amount=amount + ?",
                       session["user_id"], request.form.get("symbol"), request.form.get("shares"), request.form.get("shares"))
            db.execute("UPDATE users SET cash=? WHERE id=?", cash - cost, session["user_id"])
            db.execute("INSERT INTO history (user_id, symbol, amount, time, price) VALUES(?, ?, ?, ?, ?)", session["user_id"],
                       request.form.get("symbol"), request.form.get("shares"), strftime("%Y-%m-%d %H:%M:%S", localtime()), lookup(request.form.get("symbol"))["price"])
            return redirect("/")
        else:
            return apology("Invalid selection", 400)


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * from history WHERE user_id=?", session["user_id"])
    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")
    else:
        price = lookup(request.form.get("symbol"))
        if not price:
            return apology("Invalid Symbol", 400)
        return render_template("quoted.html", price=price)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "GET":
        return render_template("register.html")
    else:
        usernames = []
        for row in db.execute("SELECT * FROM users"):
            usernames.append(row['username'])
        if not request.form.get("username") or request.form.get("username") in usernames:
            return apology("must provide (unique) username", 400)
        elif not request.form.get("password"):
            return apology("must provide password", 400)
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 400)
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords don't match", 400)

        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"),
                   generate_password_hash(request.form.get("password")))
        return redirect("/login")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    values = []
    for row in db.execute(f'SELECT symbol FROM stocks WHERE user_id={session["user_id"]}'):
        values.append(row['symbol'])
    if request.method == "GET":
        return render_template("sell.html", values=values, ticket=request.args.get("ticket"))
    else:
        if request.form.get("symbol") not in values:
            return apology("Invalid Symbol", 400)
        if int(request.form.get("shares")) > db.execute("SELECT amount FROM stocks WHERE user_id=? AND symbol=?", session["user_id"], request.form.get("symbol"))[0]['amount']:
            return apology("Invalid count", 400)
        cost = int(request.form.get('shares')) * lookup(request.form.get("symbol"))["price"]
        cash = db.execute("SELECT cash FROM users WHERE id=?", session["user_id"])[0]['cash']
        db.execute("UPDATE stocks SET amount=amount - ? WHERE user_id=? AND symbol=?",
                   request.form.get("shares"), session["user_id"], request.form.get("symbol"))
        db.execute("INSERT INTO history (user_id, symbol, amount, time, price) VALUES(?, ?, ?, ?, ?)",
                   session["user_id"], request.form.get("symbol"), -int(request.form.get("shares")), strftime("%Y-%m-%d %H:%M:%S", localtime()), lookup(request.form.get("symbol"))["price"])
        db.execute("UPDATE users SET cash=? WHERE id=?", cash + cost, session["user_id"])
        db.execute("DELETE FROM stocks WHERE amount=0")
        return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
