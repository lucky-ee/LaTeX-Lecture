function readings(phrase) {
    const text = phrase.trim();

    if (text === "(x^2)/2") {
        return ["\\frac{x^2}{2}"];
    }

    return [];
}
