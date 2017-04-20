import tensorflow as tf
import time
import os
import datetime
from util import *
from models.cnn import CNN


# prepare raw data and embedding dict
comments, ratings = get_data(config["Paths"]["data_path"], int(config["Sizes"]["data_size"]))
x_train_raw, x_dev_raw, y_train_raw, y_dev_raw = split_data(comments, ratings, 0.2)
embedding_dict = get_embedding_dict(comments)
sent_length = max(len(c.split(' ')) for c in comments)
embedding_size = int(config["Sizes"]["embedding_size"])

# get input data
x_train = embed(x_train_raw, embedding_dict, sent_length, embedding_size)
x_dev = embed(x_dev_raw, embedding_dict, sent_length, embedding_size)
y_train = (np.arange(5) == np.array(y_train_raw)[:, None]).astype(np.float32)
y_dev = (np.arange(5) == np.array(y_dev_raw)[:, None]).astype(np.float32)

# for english corpus
# x, y = get_data_eng()
# sent_length = 61
# embedding_size = 300
# np.random.seed(10)
# shuffle_indices = np.random.permutation(np.arange(len(y)))
# x_shuffled = x[shuffle_indices]
# y_shuffled = y[shuffle_indices]
# x_train, x_dev, y_train, y_dev = split_data(x_shuffled, y_shuffled, 0.5)

graph = tf.Graph()
with graph.as_default():
    sess = tf.Session()
    with sess.as_default():
        # model = Softmax(
        #     sent_length=sent_length,
        #     class_num=2,
        #     embedding_size=embedding_size,
        #     l2_lambda=0.0
        # )
        model = CNN(
            sent_length=sent_length,
            class_num=5,
            embedding_size=embedding_size,
            l2_lambda=0,
            filter_num=128,
            filter_sizes=[1, 2, 3]
        )

        global_step = tf.Variable(0, name="global_step", trainable=False)
        optimizer = tf.train.AdamOptimizer(1e-3)
        grads_and_vars = optimizer.compute_gradients(model.loss)
        train_op = optimizer.apply_gradients(grads_and_vars, global_step=global_step)

        timestamp = str(int(time.time()))
        out_dir = os.path.abspath(os.path.join("D:\\", "runs", timestamp))
        print("Writing to {}\n".format(out_dir))

        # Keep track of gradient values and sparsity (optional)
        grad_summaries = []
        for g, v in grads_and_vars:
            if g is not None:
                grad_hist_summary = tf.summary.histogram("{}/grad/hist".format(v.name), g)
                sparsity_summary = tf.summary.scalar("{}/grad/sparsity".format(v.name), tf.nn.zero_fraction(g))
                grad_summaries.append(grad_hist_summary)
                grad_summaries.append(sparsity_summary)
        grad_summaries_merged = tf.summary.merge(grad_summaries)

        # Summaries for loss and accuracy
        loss_summary = tf.summary.scalar("loss", model.loss)
        acc_summary = tf.summary.scalar("accuracy", model.accuracy)

        # Train Summaries
        train_summary_op = tf.summary.merge([loss_summary, acc_summary, grad_summaries_merged])
        train_summary_dir = os.path.join(out_dir, "summaries", "train")
        train_summary_writer = tf.summary.FileWriter(train_summary_dir, sess.graph)
        # Dev summaries
        dev_summary_op = tf.summary.merge([loss_summary, acc_summary])
        dev_summary_dir = os.path.join(out_dir, "summaries", "dev")
        dev_summary_writer = tf.summary.FileWriter(dev_summary_dir, sess.graph)

        # Checkpoint directory. Tensorflow assumes this directory already exists so we need to create it
        checkpoint_dir = os.path.abspath(os.path.join(out_dir, "checkpoints"))
        checkpoint_prefix = os.path.join(checkpoint_dir, "model")
        if not os.path.exists(checkpoint_dir):
            os.makedirs(checkpoint_dir)
        saver = tf.train.Saver(tf.all_variables())

        sess.run(tf.global_variables_initializer())


        def train_step(x_batch, y_batch):
            feed_dict = {
                model.input_x: x_batch,
                model.input_y: y_batch,
                model.dropout_keep_prob: 1
            }
            _, step, summaries, loss, accuracy = sess.run(
                [train_op, global_step, train_summary_op, model.loss, model.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            train_summary_writer.add_summary(summaries, step)


        def dev_step(x_batch, y_batch, writer=None):
            feed_dict = {
                model.input_x: x_batch,
                model.input_y: y_batch,
                model.dropout_keep_prob: 1
            }
            step, summaries, loss, accuracy = sess.run(
                [global_step, dev_summary_op, model.loss, model.accuracy],
                feed_dict)
            time_str = datetime.datetime.now().isoformat()
            print("{}: step {}, loss {:g}, acc {:g}".format(time_str, step, loss, accuracy))
            if writer:
                writer.add_summary(summaries, step)

        # Generate batches
        batches = batch_iter(
            list(zip(x_train, y_train)), 64, 100)
        batch_num_per_epoch = int(len(x_train) / 64) + 1
        # Training loop. For each batch...
        for batch in batches:
            x_batch, y_batch = zip(*batch)
            train_step(x_batch, y_batch)
            current_step = tf.train.global_step(sess, global_step)
            if current_step % batch_num_per_epoch == 0:
                epoch_num = int(current_step / batch_num_per_epoch)
                print("\nEpoch:" + str(epoch_num))
                print("\nEvaluation:")
                dev_step(x_dev, y_dev, writer=dev_summary_writer)
                print("")
                path = saver.save(sess, checkpoint_prefix, global_step=current_step)
                print("Saved model checkpoint to {}\n".format(path))
