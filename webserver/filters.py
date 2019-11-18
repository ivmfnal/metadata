def sample(inputs, params):
    inp = inputs[0]
    fraction = params[0]
    x = 0.0
    for f in inp:
        x += fraction
        if x >= 1.0:
            x -= 1.0
            yield f
            
