import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd
from pytz import timezone

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    user = session["user_id"]

    portfolio = db.execute("SELECT * FROM portfolio WHERE user_id = ?", user)

    for row in portfolio:
        # For each stock calculate current price and value
        stock = row["stock"]
        share = row["shares"]
        price = lookup(stock)["price"]
        value = price * share
        id = row["stock_id"]
        # If stock already exists or not
        if share == 0:
            db.execute("DELETE FROM portfolio WHERE user_id = ? AND stock = ? AND shares = 0 AND stock_id = ?", user, stock, id)
        else:
            db.execute("UPDATE portfolio SET share_price = ?, value = ? WHERE user_id = ? AND stock = ? AND stock_id = ?",
                       price, value, user, stock, id)
    # Get balance
    balance = db.execute("SELECT cash FROM users WHERE id = ?", user)[0]["cash"]
    # Get value of all stocks
    total_stock_value = db.execute("SELECT SUM(value) as sum FROM portfolio WHERE user_id = ?", user)[0]["sum"]
    if type(total_stock_value) == float:
        total_stock_value = total_stock_value
    else:
        total_stock_value = 0

    assets = balance + total_stock_value
    # Update value of assets for user
    db.execute("UPDATE users SET assets = ? WHERE id = ?", assets, user)
    # Get all data needed for index.html
    data = db.execute("SELECT cash, assets FROM users WHERE id = ?", user)
    person = db.execute("SELECT username FROM users WHERE id = ?", user)[0]["username"]
    portfolio_new = db.execute("SELECT * FROM portfolio WHERE user_id = ?", user)

    return render_template("index.html", person=person, portfolio=portfolio_new, data=data)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    user = session["user_id"]
    # Create list of owned stocks
    dict = db.execute("SELECT stock FROM portfolio WHERE user_id = ?", user)
    list = []
    for row in dict:
        list.append(row["stock"])

    if request.method == "GET":
        return render_template("buy.html")

    if request.method == "POST":
        # List all required variables
        symbol = request.form.get("symbol")
        val = request.form.get("shares")

        if not val.isnumeric():
            return apology("You did not return a valid number of shares", 400)
        elif int(val) <= 0:
            return apology("You did not return a valid number of shares", 400)
        else:
            shares = int(val)

        # Check user input
        if not symbol.isalpha() or not symbol:
            return apology("You did not enter a valid stock", 400)

        apireturn = lookup(symbol)

        if not apireturn:
            return apology("No Stock was Found", 400)

        price = apireturn["price"]
        value = price * shares
        balance = db.execute("SELECT cash FROM users WHERE id = ?", user)[0]["cash"]

        if value > balance:
            return apology("Insufficient funds to make purchase")
        # Get current datetime
        now = datetime.now()
        time = now.astimezone(timezone('Asia/Kuala_Lumpur'))
        # Log transaction
        db.execute("INSERT INTO transactions (user_id, stock, shares, type, share_price_time, cost, time) VALUES (?, ?, ?, 'BUY', ?, ?, ?)",
                   user, symbol, shares, price, value, time.strftime("%I:%M:%S %p %d/%m/%Y"))
        # Calculate and update balance after transaction
        balance -= value
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, user)
        # Check if the user already owns the same stock or not
        if symbol not in list:
            db.execute("INSERT INTO portfolio (user_id, stock, shares, share_price, value) VALUES (?, ?, ?, ?, ?)",
                       user, symbol, shares, price, value)
        elif symbol in list:
            shares += int(db.execute("SELECT shares FROM portfolio WHERE stock = ? AND user_id = ?", symbol, user)[0]["shares"])
            value = price * shares
            db.execute("UPDATE portfolio SET shares = ?, value = ? WHERE user_id = ? AND stock = ?", shares, value, user, symbol)

        return redirect("/")


@app.route("/history")
@login_required
def history():
    user = session["user_id"]
    # Get transactions data
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = ?", user)
    return render_template("history.html", transactions=transactions)


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

    if request.method == "POST":
        symbol = request.form.get("symbol")
        qoute = lookup(symbol)

        if not qoute:
            return apology("Stock is not found")

        person = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])[0]["username"]
        return render_template("quoted.html", qoute=qoute, person=person)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    session.clear()

    if request.method == "POST":
        # Get user input
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        # Check user input
        if len(username) == 0:
            return apology("Username field is empty!", 400)

        if len(password) == 0:
            return apology("Password field is empty!", 400)

        if confirmation != password:
            return apology("Password does not match!", 400)

        row = db.execute("SELECT * FROM users WHERE username = ?", username)

        if len(row) != 0:
            return apology("Username is already taken", 400)
        # Generate hash password
        hashcode = generate_password_hash(password)
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", username, hashcode)
        # Set user id
        session["user_id"] = db.execute("SELECT id FROM users WHERE username = ? AND hash = ?", username, hashcode)[0]["id"]

        return redirect("/")

    if request.method == "GET":
        return render_template("register.html")

    return apology("You shouldn't be here, you're lost!", 400)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user = session["user_id"]
    # Create list of owned stocks
    dict = db.execute("SELECT stock FROM portfolio WHERE user_id = ?", user)
    list = []
    for row in dict:
        list.append(row["stock"])

    if request.method == "GET":
        return render_template("sell.html", list=dict)

    if request.method == "POST":
        # Get and check user input
        symbol = request.form.get("symbol")
        if not symbol or symbol == "NULL" or symbol not in list:
            return apology(symbol)

        price = lookup(symbol)
        if not price:
            return apology("No Stock was Found")

        # Get number of shares
        oshare = int(db.execute("SELECT shares FROM portfolio WHERE stock = ? AND user_id = ?", symbol, user)[0]["shares"])
        share = int(request.form.get("shares"))

        if share <= 0:
            return apology("That number of shares cannot be purchased")
        elif share > oshare:
            return apology("You do not own that number of shares")

        # Calculate share price
        share_price_time = price["price"]
        cost = price["price"] * share
        # Get time and create transaction
        now = datetime.now()
        time = now.astimezone(timezone('Asia/Kuala_Lumpur'))
        db.execute("INSERT INTO transactions (user_id, stock, shares, type, share_price_time, cost, time) VALUES (?, ?, ?, 'SELL', ?, ?, ?)",
                   user, symbol, -share, share_price_time, cost, time.strftime("%I:%M:%S %p %d/%m/%Y"))
        # Update portfolio
        new_shares = oshare - share
        db.execute("UPDATE portfolio SET shares = ? WHERE user_id = ? AND stock = ?", new_shares, user, symbol)
        # Update balance after transaction
        balance = db.execute("SELECT cash FROM users WHERE id = ?", user)[0]["cash"]
        balance += cost
        db.execute("UPDATE users SET cash = ? WHERE id = ?", balance, user)

        return redirect("/")

