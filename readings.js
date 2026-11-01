function readings(phrase) {
    const text = phrase.trim();

    const parts = text.split("/");

    if (parts.length !== 2) {
        return [];
    }

    let numerator = parts[0].trim();
    const denominator = parts[1].trim();

    if (numerator.startsWith("(") && numerator.endsWith(")")) {
        numerator = numerator.slice(1, -1).trim();
    }

    const simpleTerm = /^(?:[a-zA-Z]|\d+)(?:\^\d+)?$/;

    if (!simpleTerm.test(numerator) || !simpleTerm.test(denominator)) {
        return [];
    }

    return [`\\frac{${numerator}}{${denominator}}`];
}
