import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

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


@app.route("/", methods=["GET", "POST"])
@login_required
def index():
    """Show portfolio of stocks"""

    # Get cash amount
    cash = db.execute("SELECT cash FROM users WHERE id=(?)", session["user_id"])
    cash = float(cash[0]["cash"])
    total_portofolio = cash

    # Get non zero stocks portofolio for current user
    stocks = db.execute(
        "SELECT symbol, name, SUM(amount) AS total_amount FROM transactions WHERE userid=(?) GROUP BY symbol HAVING total_amount > 0", session["user_id"])

    # Calculate value of each stock in portofolio
    for stock in stocks:
        price = lookup(stock["symbol"])["price"]
        total_portofolio += price * stock["total_amount"]
        stock.update({"total": price * stock["total_amount"]})
        stock.update({"price": price})

    return render_template("index.html", cash=cash, stocks=stocks, total_portofolio=total_portofolio)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy stocks."""

    # Page reached via POST
    if request.method == "POST":

        # Check if symbol is valid
        if not lookup(request.form.get("symbol")):
            return apology("missing symbol", 400)

        # Check if shares exists
        if not request.form.get("shares"):
            return apology("missing number of shares", 400)

        # Check if no of shares is integer
        try:
            shares = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid number of shares", 400)

        if shares < 1:
            return apology("invalid number of shares", 400)

        # Check if enough cash on hand for the current transaction
        cash = db.execute("SELECT cash FROM users WHERE id = (?)", session["user_id"])
        cash = float(cash[0]["cash"])

        price = lookup(request.form.get("symbol"))["price"]
        if price * shares > cash:
            return apology("not enough cash on hand", 403)

        cash -= shares * price

        # Write data to database
        db.execute("UPDATE users SET cash=(?) WHERE id=(?)", cash, session["user_id"])
        db.execute("INSERT INTO transactions(userid, symbol, name, amount, price) VALUES((?),(?),(?),(?),(?))", session["user_id"], lookup(
            request.form.get("symbol"))["symbol"], lookup(request.form.get("symbol"))["name"], shares, price)

        # Message
        flash("Bought")
        return redirect("/")

    # Page reached via GET
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # Select data from database
    stocks = db.execute("SELECT symbol, amount, price, time FROM transactions WHERE userid=(?)", session["user_id"])
    return render_template("history.html", stocks=stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username=(?)", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("Login successful")
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
    flash("Successfully logged out")
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # Page reached via POST
    if request.method == "POST":

        # Check if symbol is valid
        if not lookup(request.form.get("symbol")):
            return apology("invalid symbol", 400)

        # Return values to quoted
        else:
            return render_template("quoted.html", share=lookup(request.form.get("symbol")))

    # Page reached via GET
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure passwords match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("provided passwords do not match", 400)

        # Ensure username does not alerady exist
        if len(db.execute("SELECT * FROM users WHERE username=(?)", request.form.get("username"))) != 0:
            return apology("username already taken", 400)

        # Input data into table
        db.execute("INSERT INTO users(username, hash) VALUES((?),(?))", request.form.get(
            "username"), generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("/register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    if request.method == "POST":

        # Check if symbol is valid
        if not lookup(request.form.get("symbol")):
            return apology("invalid symbol", 400)

        # Check if shares exists
        if not request.form.get("shares"):
            return apology("must enter number of shares", 400)

        # Check number of shares
        try:
            no_shares = int(request.form.get("shares"))
        except ValueError:
            return apology("invalid number of shares", 400)
        if no_shares < 1:
            return apology("invalid number of shares", 400)

        # Get data from database
        shares = db.execute(
            "SELECT symbol, SUM(amount) AS total_amount FROM transactions WHERE userid=(?) GROUP BY symbol HAVING total_amount > 0", session["user_id"])
        cash = db.execute("SELECT cash FROM users WHERE id=(?)", session["user_id"])
        cash = float(cash[0]["cash"])
        share_price = lookup(request.form.get("symbol"))["price"]

        # Check if symbol in portofolio and if found update data
        for share in shares:
            if share["symbol"] == lookup(request.form.get("symbol"))["symbol"]:
                if share["total_amount"] >= no_shares:
                    flash("Sold")
                    cash += no_shares * share_price
                    db.execute("UPDATE users SET cash=(?) WHERE id=(?)", cash, session["user_id"])
                    no_shares *= -1
                    db.execute("INSERT INTO transactions(userid, symbol, name, amount, price) VALUES((?),(?),(?),(?),(?))",
                               session["user_id"], share["symbol"], lookup(request.form.get("symbol"))["name"], no_shares, share_price)
                    return redirect("/")
                else:
                    return apology("not enough shares", 400)

        return apology("symbol not found", 403)

    # Reach via GET
    else:
        shares = db.execute(
            "SELECT symbol, SUM(amount) AS total_amount FROM transactions WHERE userid=(?) GROUP BY symbol HAVING total_amount > 0", session["user_id"])
        return render_template("sell.html", shares=shares)


@app.route("/change_pass", methods=["GET", "POST"])
@login_required
def change_pass():
    """Change password for current user"""

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("password"):
            return apology("must provide current password", 403)

        # Ensure password was submitted
        elif not request.form.get("new_password"):
            return apology("must provide new password", 403)

        elif not request.form.get("confirmation"):
            return apology("must confirm new password", 403)

        # Ensure passwords match
        elif request.form.get("new_password") != request.form.get("confirmation"):
            return apology("provided passwords do not match", 403)

        # Ensure password is correct
        hash = db.execute("SELECT hash FROM users WHERE id=(?)", session["user_id"])
        if not check_password_hash(hash[0]["hash"], request.form.get("password")):
            return apology("incorrect password", 403)

        flash("Password changed successfully")

        # Input data into table
        db.execute("UPDATE users SET hash=(?) WHERE id=(?)", generate_password_hash(
            request.form.get("new_password")), session["user_id"])

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("/change_pass.html")


@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    """Add funds for current user"""

    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("cash"):
            return apology("must provide cash amount", 403)

        # Check if integer
        try:
            cash = int(request.form.get("cash"))
        except ValueError:
            return apology("invalid amount", 403)

        # Check if positive
        if cash < 1:
            return apology("invalid amount", 403)

        # Input data into table
        current_cash = db.execute("SELECT cash FROM users WHERE id=(?)", session["user_id"])
        cash += current_cash[0]["cash"]
        db.execute("UPDATE users SET cash=(?) WHERE id=(?)", cash, session["user_id"])

        flash("Cash added")
        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("/add.html")