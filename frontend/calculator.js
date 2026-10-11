// calculator.js - a small, safe maths engine (no eval!)
// Understands: + - * / ^ ( )  numbers  pi  e
// and the functions sin cos tan asin acos atan sqrt ln log abs

const FUNCTIONS = ["sin", "cos", "tan", "asin", "acos", "atan", "sqrt", "ln", "log", "abs"];

function tokenize(text) {
  const tokens = [];
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === " ") { i++; continue; }
    if (/[0-9.]/.test(ch)) {
      // a number like 42, 3.14, .5 or 1.5e+21
      const match = text.slice(i).match(/^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?/i);
      if (!match) throw new Error("Bad number");
      tokens.push({ type: "num", value: parseFloat(match[0]) });
      i += match[0].length;
      continue;
    }
    if (/[a-z]/i.test(ch)) {
      let word = "";
      while (i < text.length && /[a-z]/i.test(text[i])) word += text[i++];
      tokens.push({ type: "word", value: word.toLowerCase() });
      continue;
    }
    if ("+-*/^()".includes(ch)) { tokens.push({ type: "op", value: ch }); i++; continue; }
    throw new Error("Unknown symbol: " + ch);
  }
  return tokens;
}

function evaluate(expression, mode = "deg") {
  const text = expression.replace(/×/g, "*").replace(/÷/g, "/").replace(/π/g, "pi").replace(/−/g, "-");
  if (text.trim() === "") throw new Error("Nothing to calculate");
  const tokens = tokenize(text);
  let pos = 0;
  const peek = () => tokens[pos];
  const take = () => tokens[pos++];
  const toRad = (x) => (mode === "deg" ? (x * Math.PI) / 180 : x);
  const fromRad = (x) => (mode === "deg" ? (x * 180) / Math.PI : x);

  // expression := term (("+" | "-") term)*
  function parseExpression() {
    let value = parseTerm();
    while (peek() && (peek().value === "+" || peek().value === "-")) {
      const op = take().value;
      const right = parseTerm();
      value = op === "+" ? value + right : value - right;
    }
    return value;
  }

  // term := unary (("*" | "/") unary)*
  function parseTerm() {
    let value = parseUnary();
    while (peek() && (peek().value === "*" || peek().value === "/")) {
      const op = take().value;
      const right = parseUnary();
      if (op === "/" && right === 0) throw new Error("Cannot divide by zero");
      value = op === "*" ? value * right : value / right;
    }
    return value;
  }

  // unary := ("-" | "+") unary | power
  function parseUnary() {
    if (peek() && (peek().value === "-" || peek().value === "+")) {
      const op = take().value;
      const value = parseUnary();
      return op === "-" ? -value : value;
    }
    return parsePower();
  }

  // power := primary ("^" unary)?      (2^3^2 = 2^9, like on paper)
  function parsePower() {
    const base = parsePrimary();
    if (peek() && peek().value === "^") {
      take();
      return Math.pow(base, parseUnary());
    }
    return base;
  }

  function expect(symbol) {
    const t = take();
    if (!t || t.value !== symbol) throw new Error("Missing " + symbol);
  }

  // primary := number | pi | e | function "(" expression ")" | "(" expression ")"
  function parsePrimary() {
    const t = take();
    if (!t) throw new Error("Expression ends too early");
    if (t.type === "num") return t.value;
    if (t.value === "(") {
      const value = parseExpression();
      expect(")");
      return value;
    }
    if (t.type === "word") {
      if (t.value === "pi") return Math.PI;
      if (t.value === "e") return Math.E;
      if (FUNCTIONS.includes(t.value)) {
        expect("(");
        const x = parseExpression();
        expect(")");
        return applyFunction(t.value, x);
      }
      throw new Error("Unknown name: " + t.value);
    }
    throw new Error("Unexpected " + t.value);
  }

  function applyFunction(name, x) {
    switch (name) {
      case "sin": return Math.sin(toRad(x));
      case "cos": return Math.cos(toRad(x));
      case "tan": return Math.tan(toRad(x));
      case "asin": return fromRad(Math.asin(x));
      case "acos": return fromRad(Math.acos(x));
      case "atan": return fromRad(Math.atan(x));
      case "sqrt":
        if (x < 0) throw new Error("Square root of a negative number");
        return Math.sqrt(x);
      case "ln":
        if (x <= 0) throw new Error("ln needs a positive number");
        return Math.log(x);
      case "log":
        if (x <= 0) throw new Error("log needs a positive number");
        return Math.log10(x);
      case "abs": return Math.abs(x);
    }
  }

  const result = parseExpression();
  if (pos < tokens.length) throw new Error("Unexpected " + tokens[pos].value);
  if (!Number.isFinite(result)) throw new Error("Result is too big or undefined");
  return Number(result.toPrecision(12));  // tidy: sin(180) gives 0, not 1.2e-16
}

// Make evaluate() available to app.js
window.Calculator = { evaluate };
