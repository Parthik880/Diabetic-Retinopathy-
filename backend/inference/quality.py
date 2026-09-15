def predict(image, model):
    return model.predict(image)


def predict_batch(images, model):
    return model.predict_batch(images)
