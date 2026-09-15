def predict(image, model):
    return model.predict(image)


def predict_batch(images, model, timing=None):
    return model.predict_batch(images, timing=timing)
