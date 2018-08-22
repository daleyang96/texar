# Copyright 2018 The Texar Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
End-to-end memory network described in
(Sukhbaatar et al.) End-To-End Memory Networks
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf

from texar.module_base import ModuleBase
from texar.modules.embedders import WordEmbedder
from texar.utils.mode import switch_dropout
from texar.modules.memory.embed_fns import \
    default_embed_fn, get_default_embed_fn_hparams

# pylint: disable=invalid-name

__all__ = [
    'MemNetBase',
    'MemNetRNNLike',
]

class MemNetSingleLayer(ModuleBase):
    """An A-C layer for memory network.

    Args:
        H (optional): The matrix :attr:`H` multiplied to :attr:`o` at the end.
        hparams (dict or HParams, optional): Memory network single layer
            hyperparameters. If it is not specified, the default hyperparameter
            setting is used. See :attr:`default_hparams` for the structure and
            default values.
    """

    def __init__(self, H=None, hparams=None):
        ModuleBase.__init__(self, hparams)

        self._H = H

    @staticmethod
    def default_hparams():
        """Returns a dictionary of hyperparameters with default values.

        Returns:
            .. code-block:: python

                {
                    "name": "memnet_single_layer"
                }

            Here:

            "name": str
                Name of the memory network single layer.
        """
        return {
            "name": "memnet_single_layer"
        }

    def _build(self, u, m, c, **kwargs):
        """An A-C operation with memory and query vector.

        Args:
            u (Tensor): The input query `Tensor` of shape `[None, dim]`.
            m (Tensor): Output of A operation. Should be in shape
                `[None, memory_size, dim]`.
            c (Tensor): Output of C operation. Should be in shape
                `[None, memory_size, dim]`.

        Returns:
            A `Tensor` of shape same as :attr:`u`.
        """
        with tf.variable_scope(self.variable_scope):
            # Input memory representation
            p = tf.matmul(m, tf.expand_dims(u, axis=2))
            p = tf.transpose(p, perm=[0, 2, 1])

            p = tf.nn.softmax(p) # equ. (1)

            # Output memory representation
            o = tf.matmul(p, c) # equ. (2)
            o = tf.squeeze(o, axis=[1])

            if self._H:
                u = tf.matmul(u, self._H) # RNN-like style
            u_ = tf.add(u, o) # u^{k+1} = H u^k + o^k

        if not self._built:
            self._add_internal_trainable_variables()
            if self._H:
                self._add_trainable_variable(self._H)
            self._built = True

        return u_

class MemNetBase(ModuleBase):
    """Base class inherited by memory networks.

    Args:
        vocab_size (int): Vocabulary size of all :attr:`embed_fn`s
            and final embedding matrix.
        input_embed_fn (function): Function implements A-operation.
            Differs from different kinds of memory network.
        output_embed_fn (function): Function implements C-operation.
            Differs from different kinds of memory network.
        query_embed_fn (function): Function implements B-operation
            (for input query).
            Differs from different kinds of memory network.
        hparams (HParams or dict, optional): Memory network base class
            hyperparameters. If it is not specified, the default hyperparameter
            setting is used. See :attr:`default_hparams` for the structure and
            default values.
    """

    def __init__(self, vocab_size, input_embed_fn, output_embed_fn,
                 query_embed_fn, hparams=None):
        ModuleBase.__init__(self, hparams)
        self._n_hops = self.hparams.n_hops
        self._dim = self.hparams.dim
        self._reludim = self.hparams.reludim
        self._memory_size = self.hparams.memory_size
        self._vocab_size = vocab_size
        self._input_embed_fn = input_embed_fn
        self._output_embed_fn = output_embed_fn
        self._query_embed_fn = query_embed_fn
        with tf.variable_scope(self.variable_scope):
            if self.hparams.need_H:
                self.H = tf.get_variable(
                    name="H", shape=[self._dim, self._dim])
            else:
                self.H = None
            self._final_matrix = tf.transpose(
                WordEmbedder(
                    vocab_size=vocab_size,
                    hparams=self.hparams.final_matrix
                ).embedding,
                name="final_matrix")

    @staticmethod
    def default_hparams():
        """
        Returns:
            .. code-block:: python

                {
                    "name": "memnet_base",
                    "n_hops": 1,
                    "dim": 100,
                    "reludim": 50,
                    "memory_size": 100,
                    "need_H": False,
                    "final_matrix": {
                        "name": "final_matrix",
                        "dim": 100,
                        "dropout_rate": 0,
                    },
                    "dropout_rate": 0,
                    "variational": False,
                }

            Here:

            "n_hops": int
                Number of hops.

            "dim": int
                Dimension of all the vectors.

            "reludim": int
                Number of elements in dim that have relu at the end of each hop.
                Should be not less than 0 and not more than :attr`"dim"`.

            "memory_size": int
                Number of elements used as the memory.

            "need_H": bool
                Whether needs to perform transform with :attr:`H` matrix at
                the end of A-C layer.

            "final_matrix": dict
                Hyperparameters of the final matrix.
                Should be same as
                :class:`~texar.modules.embedders.WordEmbedder`.

            "dropout_rate": float
                The dropout rate to apply to the output of each hop. Should
                be between 0 and 1.
                E.g., `dropout_rate=0.1` would drop out 10% of the units.

            "variational": bool
                Whether to share dropout masks after each hop like variational
                RNNs.
        """
        return {
            "name": "memnet_base",
            "n_hops": 1,
            "dim": 100,
            "reludim": 50,
            "memory_size": 100,
            "need_H": False,
            "final_matrix": {
                "name": "final_matrix",
                "dim": 100,
                "dropout_rate": 0,
            },
            "dropout_rate": 0,
            "variational": False,
        }

    def _build(self, memory, query, **kwargs):
        raise NotImplementedError

class MemNetRNNLike(MemNetBase):
    """An implementation of multi-layer end-to-end memory network
    with RNN-like weight tying described in the paper.

    If you want to customize the embed functions,
    see :func:`~texar.modules.memory.default_embed_fn` for implemention
        details.

    Args:
        vocab_size (int): Vocabulary size of all :attr:`embed_fn`s and
            final embedding matrix.
        input_embed_fn (function): Function implements A-operation.
            Default is :func:`~texar.modules.memory.default_embed_fn`.
            See default function for details.
        output_embed_fn (function): Function implements C-operation.
            Similar to :attr:`input_embed_fn`.
        query_embed_fn (function): Function implements B-operation
            (for input query).
            Similar to :attr:`input_embed_fn`.
        hparams (HParams or dict, optional): RNN-like memory network
            hyperparameters. If it is not specified, the default hyperparameter
            setting is used. See :attr:`default_hparams` for the structure and
            default values.
    """

    def __init__(self, vocab_size,
                 input_embed_fn=default_embed_fn,
                 output_embed_fn=default_embed_fn,
                 query_embed_fn=None, hparams=None):
        MemNetBase.__init__(self, vocab_size, input_embed_fn,
            output_embed_fn, query_embed_fn, hparams)
        with tf.variable_scope(self.variable_scope):
            if self._query_embed_fn:
                self.B = tf.make_template(
                    "B",
                    self._query_embed_fn,
                    vocab_size=self._vocab_size,
                    hparams=self.hparams.B,
                    create_scope_now_=True)
            else:
                self.B = None
            self.A = tf.make_template(
                "A",
                self._input_embed_fn,
                vocab_size=self._vocab_size,
                hparams=self.hparams.A,
                create_scope_now_=True)
            self.C = tf.make_template(
                "C",
                self._output_embed_fn,
                vocab_size=self._vocab_size,
                hparams=self.hparams.C,
                create_scope_now_=True)
            self.AC = MemNetSingleLayer(self.H,
                hparams={"name": "AC"})


    @staticmethod
    def default_hparams():
        """Returns a dictionary of hyperparameters with default values.

        Returns:
            .. code-block:: python

                {
                    "name": "memnet_rnnlike",
                    "n_hops": 1,
                    "dim": 100,
                    "reludim": 50,
                    "memory_size": 100,
                    "need_H": True,
                    "final_matrix": {
                        "name": "final_matrix",
                        "dim": 100,
                        "dropout_rate": 0
                    }
                    "A": default_embed_hparams,
                    "C": default_embed_hparams,
                    "B": default_embed_hparams,
                }

                default_embed_hparams = {
                    "memory_size": 100,
                    "embedding": {
                        "name": "embedding",
                        "dim": 100,
                        "initializer": None, # use default initializer
                        "dropout_rate": 0
                    },
                    "temporal_embedding": {
                        "name": "temporal_embedding",
                        "dim": 100,
                        "initializer": None, # use default initializer
                        "dropout_rate": 0
                    }
                }
        """
        hparams = MemNetBase.default_hparams()
        hparams["name"] = "memnet_rnnlike"
        hparams["need_H"] = True
        for _ in ("A", "C", "B"):
            hparams[_] = get_default_embed_fn_hparams()
        return hparams

    def _build(self, query, memory=None, soft_memory=None, **kwargs):
        """Pass the :attr:`memory` and :attr:`query` through the memory network
        and return the :attr:`logits` after the final matrix.

        Args:
            query: Query vectors as the intial input of the memory network.
                If you'd like to apply some transformation (e.g., embedding)
                on it before it's fed into the network, please add
                `query_embed_fn` when constructing this instance.
                If you do not provide `query_embed_fn`, it should be of shape
                `[batch_size, dim]`.
            memory (optional): Memory used in A/C operations. By default, it
                should be an integer tensor of shape
                `[batch_size, memory_size]`,
                containing the ids to embed if provided.
            soft_memory (optional): Soft memory used in A/C operations. By
                default, it should be a tensor of shape
                `[batch_size, memory_size, vocab_size]`,
                containing the weights used to mix the embedding vectors.
                If you'd like to apply a matrix multiplication on the memory,
                this option can also be used.
        """
        with tf.variable_scope(self.variable_scope):
            if self.B is not None:
                query = self.B(query)
            self.u = [query]
            self.m = self.A(memory, soft_memory)
            self.c = self.C(memory, soft_memory)

            keep_prob = switch_dropout(1-self.hparams.dropout_rate)
            if self.hparams.variational:
                with tf.variable_scope("variational_dropout"):
                    noise = tf.random_uniform(tf.shape(self.u[-1]))
                    random_tensor = keep_prob + noise
                    binary_tensor = tf.floor(random_tensor)
                def variational_dropout(val):
                    return tf.div(val, keep_prob) * binary_tensor

            for k in range(self._n_hops):
                u_ = self.AC(self.u[-1], self.m, self.c)
                if self._reludim == 0:
                    pass
                elif self._reludim == self._dim:
                    u_ = tf.nn.relu(u_)
                elif 0 < self._reludim < self._dim:
                    linear_part = u_[:, : self._dim - self._reludim]
                    relu_part = u_[:, self._dim - self._reludim :]
                    relued_part = tf.nn.relu(relu_part)
                    u_ = tf.concat(axis=1, values=[linear_part, relued_part])
                else:
                    raise Exception("reludim = {} is illegal".format(
                        self._reludim))
                if self.hparams.variational:
                    u_ = variational_dropout(u_)
                else:
                    u_ = tf.nn.dropout(u_, keep_prob)
                self.u.append(u_)

            logits = tf.matmul(self.u[-1], self._final_matrix)

        if not self._built:
            self._add_internal_trainable_variables()
            self._built = True

        return logits
