import numpy
import timeit
from thinc.api import NumpyOps, LSTM, PyTorchLSTM, with_padded, fix_random_seed
from thinc.util import has_torch
import pytest


@pytest.fixture(params=[1, 6])
def nI(request):
    return request.param


@pytest.fixture(params=[1, 2, 7, 9])
def nO(request):
    return request.param


def test_list2padded():
    ops = NumpyOps()
    seqs = [numpy.zeros((5, 4)), numpy.zeros((8, 4)), numpy.zeros((2, 4))]
    padded = ops.list2padded(seqs)
    arr = padded.data
    size_at_t = padded.size_at_t
    assert arr.shape == (8, 3, 4)
    assert size_at_t[0] == 3
    assert size_at_t[1] == 3
    assert size_at_t[2] == 2
    assert size_at_t[3] == 2
    assert size_at_t[4] == 2
    assert size_at_t[5] == 1
    assert size_at_t[6] == 1
    assert size_at_t[7] == 1
    unpadded = ops.padded2list(padded)
    assert unpadded[0].shape == (5, 4)
    assert unpadded[1].shape == (8, 4)
    assert unpadded[2].shape == (2, 4)


@pytest.mark.parametrize("nO,nI", [(1, 2), (2, 2), (100, 200), (9, 6)])
def test_LSTM_init_with_sizes(nO, nI):
    model = with_padded(LSTM(nO, nI)).initialize()
    for node in model.walk():
        # Check no unallocated params.
        assert node.has_param("W") is not None
        assert node.has_param("b") is not None
        assert node.has_param("initial_hiddens") is not None
        assert node.has_param("initial_cells") is not None
    for node in model.walk():
        # Check param sizes.
        if node.has_param("W"):
            W = node.get_param("W")
            assert W.shape == (nO * 4, nO + nI)
        if node.has_param("b"):
            b = node.get_param("b")
            assert b.shape == (nO * 4,)
        if node.has_param("initial_hiddens"):
            initial_hiddens = node.get_param("initial_hiddens")
            assert initial_hiddens.shape == (nO,)
        if node.has_param("initial_cells"):
            initial_cells = node.get_param("initial_cells")
            assert initial_cells.shape == (nO,)


def test_LSTM_fwd_bwd_shapes(nO, nI):
    nO = 1
    nI = 2
    X = numpy.asarray([[0.1, 0.1], [-0.1, -0.1], [1.0, 1.0]], dtype="f")
    model = with_padded(LSTM(nO, nI)).initialize(X=[X])
    ys, backprop_ys = model([X], is_train=False)
    dXs = backprop_ys(ys)
    assert numpy.vstack(dXs).shape == numpy.vstack([X]).shape


def test_LSTM_learns():
    fix_random_seed(0)

    nO = 2
    nI = 2

    def sgd(key, weights, gradient):
        weights -= 0.001 * gradient
        return weights, gradient * 0

    model = with_padded(LSTM(nO, nI))
    X = [[0.1, 0.1], [0.2, 0.2], [0.3, 0.3]]
    Y = [[0.2, 0.2], [0.3, 0.3], [0.4, 0.4]]
    X = [model.ops.asarray(x, dtype="f").reshape((1, -1)) for x in X]
    Y = [model.ops.asarray(y, dtype="f").reshape((1, -1)) for y in Y]
    model = model.initialize(X, Y)
    Yhs, bp_Yhs = model.begin_update(X)
    loss1 = sum([((yh - y) ** 2).sum() for yh, y in zip(Yhs, Y)])
    Yhs, bp_Yhs = model.begin_update(X)
    dYhs = [yh - y for yh, y in zip(Yhs, Y)]
    dXs = bp_Yhs(dYhs)
    model.finish_update(sgd)
    Yhs, bp_Yhs = model.begin_update(X)
    dYhs = [yh - y for yh, y in zip(Yhs, Y)]
    dXs = bp_Yhs(dYhs)  # noqa: F841
    loss2 = sum([((yh - y) ** 2).sum() for yh, y in zip(Yhs, Y)])
    assert loss1 > loss2, (loss1, loss2)


@pytest.mark.skip
def test_benchmark_LSTM_fwd():
    nO = 128
    nI = 128
    n_batch = 1000
    batch_size = 30
    seq_len = 30
    lengths = numpy.random.normal(scale=10, loc=30, size=n_batch * batch_size)
    lengths = numpy.maximum(lengths, 1)
    batches = []
    uniform_lengths = False
    model = with_padded(LSTM(nO, nI)).initialize()
    for batch_lengths in model.ops.minibatch(batch_size, lengths):
        batch_lengths = list(batch_lengths)
        if uniform_lengths:
            seq_len = max(batch_lengths)
            batch = [
                numpy.asarray(
                    numpy.random.uniform(0.0, 1.0, (int(seq_len), nI)), dtype="f"
                )
                for _ in batch_lengths
            ]
        else:
            batch = [
                numpy.asarray(
                    numpy.random.uniform(0.0, 1.0, (int(seq_len), nI)), dtype="f"
                )
                for seq_len in batch_lengths
            ]
        batches.append(batch)
    start = timeit.default_timer()
    for Xs in batches:
        ys, bp_ys = model.begin_update(list(Xs))
        # _ = bp_ys(ys)
    end = timeit.default_timer()
    n_samples = n_batch * batch_size
    print(
        "--- %i samples in %s seconds (%f samples/s, %.7f s/sample) ---"
        % (n_samples, end - start, n_samples / (end - start), (end - start) / n_samples)
    )


def test_lstm_init():
    model = with_padded(LSTM(2, 2, bi=True)).initialize()
    model.initialize()
    with pytest.raises(NotImplementedError):
        with_padded(LSTM(2, dropout=0.2))


@pytest.mark.skipif(not has_torch, reason="needs PyTorch")
def test_pytorch_lstm_init():
    model = with_padded(PyTorchLSTM(2, 2, depth=0)).initialize()
    assert model.name == "with_padded(noop)"
