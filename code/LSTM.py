# -*- coding: utf-8 -*-
"""Copy of lstm_final.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1QXEgtmv4v4tnLMpq6T-oh3x0LSZ8zn1w
"""

# !pip install wandb

import wandb
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np
import matplotlib.pyplot as plt
import pandas as pd
import random
import re
import nltk
nltk.download('punkt')
from nltk.tokenize import word_tokenize
from nltk.translate.bleu_score import sentence_bleu
from torch.nn.functional import normalize as l2_norm
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

# Define the hyperparameters and their respective values in a dictionary format
# hyperparameter_defaults = dict(
#     batch_size = [32, 64, 128],
#     embedding_dim = [300],
#     hidden_dim = [256, 512, 1028],
#     learning_rate = [0.01],
#     max_sent_length = [20, 30],
#     num_epochs = [20, 30],
#     num_layers = [2, 3],
#     run_type = ['test']
# )
hyperparameter_defaults = dict(
    batch_size = [32,64,128],
    embedding_dim = [300],
    hidden_dim = [512],
    num_epochs = [100],
    num_layers = [2, 3],
    activation = [ "lsf" , "l2_norm"],
    run_type = ['REAL']
)
# Define the metric to be optimized and the optimization goal
metric = dict(
    goal = 'maximize',
    name = 'bleu_score'
)
# Set up the sweep configuration using wandb.sweep()
sweep_config = {
    'method': 'grid',
    'metric': metric,
    'parameters': hyperparameter_defaults,
    'program': 'train.py'
}

# HYPERPARAMETERS
# Set random seed for reproducibility
random.seed(42)
torch.manual_seed(42)

# Define the start and end tokens
START_TOKEN = "<s>"
END_TOKEN = "</s>"
START_TOKEN_IDX = 0
END_TOKEN_IDX = 1
PAD_TOKEN = "<p>"
PAD_TOKEN_IDX = 2
UNK_TOKEN="UNK"
UNK_TOKEN_IDX = 3
# # Define the model hyperparameters
config = {
    "embedding_dim": 300,
    "hidden_dim": 512,
    "batch_size": 128,
    "num_epochs": 250,
    "num_layers": 2,
    "run_type": "REAL",
    "activation": "lsf"
}
MAX_SENT_LENGTH = 8
# EMBEDDING_DIM = config["embedding_dim"]
# HIDDEN_DIM = config["hidden_dim"]
# BATCH_SIZE = config["batch_size"]
# NUM_EPOCHS = config["num_epochs"]
# NUM_LAYERS = config["num_layers"]
weights = [(1, 0, 0, 0), (0.5, 0.5), (0.33, 0.33, 0.33, 0), (0.25, 0.25, 0.25, 0.25),(0.2,0.2,0.2,0.2,0.2),(0.16,0.16,0.16,0.16,0.16,0.16),(0.14,0.14,0.14,0.14,0.14,0.14,0.14),(0.125,0.125,0.125,0.125,0.125,0.125,0.125,0.125)]

wandb.init(entity = "lakshmipathi-balaji",   # wandb username. (NOT REQUIRED ARG. ANYMORE, it fetches from initial login)
           project = "inlp-project", # wandb project name. New project will be created if given project is missing.
           config = config         # Config dict
          )
wandb.run.name = f"{config['run_type']}_{config['num_epochs']}_ON_SPLITS_REAL_FINAL_lsf_max=8"

# Define the model architecture
class Encoder(nn.Module):
    def __init__(self, input_size, embedding_dim, hidden_dim,NUM_LAYERS):
        super(Encoder, self).__init__()
        self.hidden_dim = hidden_dim
        self.embedding = nn.Embedding(input_size, embedding_dim,padding_idx=PAD_TOKEN_IDX)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim,num_layers=NUM_LAYERS,dropout=0.1)

    def forward(self, input_seqs):
        embedded = self.embedding(input_seqs)
        embedded = embedded.to(device)
        outputs, (hidden, cell) = self.lstm(embedded)
        outputs = outputs.to(device)
        hidden = hidden.to(device)
        cell = cell.to(device)
        return hidden, cell

class Decoder(nn.Module):
    def __init__(self, output_size, embedding_dim, hidden_dim,NUM_LAYERS, ACTIVATION):
        super(Decoder, self).__init__()
        self.hidden_dim = hidden_dim
        self.embedding = nn.Embedding(output_size, embedding_dim, padding_idx=PAD_TOKEN_IDX)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim,num_layers=NUM_LAYERS,dropout=0.1)
        self.fc = nn.Linear(hidden_dim, output_size)
        self.log_softmax = nn.LogSoftmax(dim=1)
        self.ACTIVATION = ACTIVATION

    def forward(self, input, hidden, cell):
        embedded = self.embedding(input)
        embedded = embedded.to(device)
        output, (hidden, cell) = self.lstm(embedded, (hidden, cell))
        output = output.to(device)
        hidden = hidden.to(device)
        cell = cell.to(device)
        output = self.fc(output)
        if(self.ACTIVATION == "lsf"):
          output = self.log_softmax(output)
        elif(self.ACTIVATION == "l2_norm"):
          output = l2_norm(output)
        return output, hidden, cell

def train(input_seqs, target_seqs, encoder, decoder, encoder_optimizer, decoder_optimizer, criterion, word_to_idx):
    loss = 0
    encoder_optimizer.zero_grad()
    decoder_optimizer.zero_grad()
    for i in range(len(input_seqs)):
        encoder_hidden, encoder_cell = encoder(input_seqs[i])
        decoder_input = torch.tensor([START_TOKEN_IDX])
        decoder_input  = decoder_input.to(device)
        decoder_output = torch.tensor([])
        decoder_hidden = encoder_hidden
        decoder_cell = encoder_cell
        for j in range(1,len(target_seqs[i])):
            decoder_output, decoder_hidden, decoder_cell = decoder(decoder_input, decoder_hidden, decoder_cell)
            loss += criterion(decoder_output[-1].squeeze(), target_seqs[i][j])
            _ = target_seqs[i][j].unsqueeze(0)
            _ = torch.tensor(_)
            _ = _.to(device)
            decoder_input = torch.cat((decoder_input, _))
        decoder_output = decoder_output.to(device)
    loss.backward()
    encoder_optimizer.step()
    decoder_optimizer.step()
    
    return loss.item() / len(input_seqs)

# Use the trained model to translate a sentence
def translate_sentence(set_sentence, encoder, decoder, word_to_idx, idx_to_word):
    with torch.no_grad():
      input_seq = []
      for i in range(len(set_sentence)):
          input_seq.append(torch.tensor([word_to_idx[word] if word in word_to_idx.keys() else word_to_idx[UNK_TOKEN] for word in set_sentence[i][0].split()]).to(device))
          # input_seq += [word_to_idx[set_sentence[i]] if set_sentence[i] in word_to_idx.keys() else UNK_TOKEN_IDX]
      # input_seq = torch.tensor(input_seq).to(device)

      output_sentences = []
      for i in range(len(input_seq)):
          encoder_hidden, encoder_cell = encoder(input_seq[i])
          decoder_input = torch.tensor([START_TOKEN_IDX])
          decoder_input  = decoder_input.to(device)
          decoder_hidden = encoder_hidden
          decoder_cell = encoder_cell
          output_sentence = ""
          while True:
              output, decoder_hidden, decoder_cell = decoder(decoder_input, decoder_hidden, decoder_cell)
              top_idx = []
              _, top_idx = output[-1].topk(1)
              if top_idx[0].item() == END_TOKEN_IDX or top_idx[0].item() == PAD_TOKEN_IDX:
                  break
              else:
                  output_sentence += idx_to_word[top_idx[0].item()] + " "
                  if output_sentence.split()[-3:] == output_sentence.split()[-6:-3]:
                      break
                  top_idx = top_idx.to(device)
                  decoder_input = torch.cat((decoder_input, top_idx), 0).to(device)
          output_sentences.append(output_sentence)
      return output_sentences

def remove_punctuations(text):
    return re.sub(
        r'(!|"|\#|\$|%|&|\'|\(|\)|\*|\+|,|-|—|’|\.|\/|:|;|<|=|>|\?|@|\[|\\|\]|\^|_|‘|\{|\||\}|~{1,})', r' ', text
    )
def prepare_data():
    train_tuple_set = []
    test_tuple_set = []
    valid_tuple_set = []
    with open('./train1.txt') as f:
        train = f.read()
        for line in train.split('\n'):
            if line:
                line = line.split('\t')
                cleaned_line = []
                index = 0
                if len(line) == 2:
                    for sent in line:
                        sent = remove_punctuations(sent)
                        word_list = word_tokenize(sent)
                        sent = ' '.join(w.lower() for w in word_list)
                        if(len(sent.split()) > MAX_SENT_LENGTH):
                            index = 1
                            break
                        elif(len(sent.split()) < MAX_SENT_LENGTH):
                            # pad the sequence with <pad> token until it reaches MAX_SENT_LENGTH
                            sent = sent + (' '+PAD_TOKEN+' ')*(MAX_SENT_LENGTH-len(sent.split()))
                        cleaned_line.append(sent)
                    if index == 0:
                        train_tuple_set.append(tuple(cleaned_line))

    with open('./test1.txt') as f:
        test = f.read()
        for line in test.split('\n'):
            if line:
                line = line.split('\t')
                cleaned_line = []
                index = 0
                if len(line) == 2:
                    for sent in line:
                        sent = remove_punctuations(sent)
                        word_list = word_tokenize(sent)
                        sent = ' '.join(w.lower() for w in word_list)
                        if(len(sent.split()) > MAX_SENT_LENGTH):
                            index = 1
                            break
                        elif(len(sent.split()) < MAX_SENT_LENGTH):
                            sent = sent + (' '+PAD_TOKEN+' ')*(MAX_SENT_LENGTH-len(sent.split()))
                        if(len(sent.split()) == 0):
                            index = 1
                        cleaned_line.append(sent)
                    if index == 0:
                        test_tuple_set.append(tuple(cleaned_line))

    with open('./dev1.txt') as f:
        valid = f.read()
        for line in valid.split('\n'):
            if line:
                line = line.split('\t')
                cleaned_line = []
                index = 0
                if len(line) == 2:
                    for sent in line:
                        sent = remove_punctuations(sent)
                        word_list = word_tokenize(sent)
                        sent = ' '.join(w.lower() for w in word_list)
                        if(len(sent.split()) > MAX_SENT_LENGTH):
                            index = 1
                            break
                        elif(len(sent.split()) < MAX_SENT_LENGTH):
                            sent = sent + (' '+PAD_TOKEN+' ')*(MAX_SENT_LENGTH-len(sent.split()))
                        cleaned_line.append(sent)
                    if index == 0:
                        valid_tuple_set.append(tuple(cleaned_line))
    return train_tuple_set, valid_tuple_set, test_tuple_set

from nltk.translate.bleu_score import sentence_bleu
def bleu_score(references, candidates,index): # type: ignore
    score = [0]*len(weights)
    for i in range(len(references)):
        for j,w in enumerate(weights):
            temp_score = sentence_bleu([references[i]], candidates[i], weights=w)
            # add temp score truncated to 2 decimal places to score[j]
            score[j] += temp_score # type: ignore
    if (index=='val'):
      with open('val_translations.txt','w') as f:
        for i in range(len(references)):
          ref_line = ' '.join([str(s) for s in references[i]])
          cand_line = ' '.join([str(s) for s in candidates[i]])
          f.write(ref_line+'    '+cand_line+'\n')
    if (index=='test'):
      with open('test_translations.txt','w') as f:
        for i in range(len(references)):
          ref_line = ' '.join([str(s) for s in references[i]])
          cand_line = ' '.join([str(s) for s in candidates[i]])
          f.write(ref_line+'    '+cand_line+'\n')
    if (index=='train'):
      with open('train_translations.txt','w') as f:
        for i in range(len(references)):
          ref_line = ' '.join([str(s) for s in references[i]])
          cand_line = ' '.join([str(s) for s in candidates[i]])
          f.write(ref_line+'    '+cand_line+'\n')
    for i in range(len(score)):
        score[i] = score[i]/len(references) # type: ignore
        score[i] = round(score[i],6)
    return score

def evaluate(validation_data,translated_sentence,index):
    for i in range(len(validation_data)):
        validation_data[i] = (validation_data[i][0],validation_data[i][1].replace(PAD_TOKEN,""))
    predicted_sentences = []
    for i in translated_sentence:
        predicted_sentences.append(i.split())

    target_sentences = []
    for i in validation_data:
        target_sentences.append(i[1].replace(PAD_TOKEN,"").split())
    score = bleu_score(target_sentences,predicted_sentences,index)
    return(score)

def save_model(model, filepath):
    """
    Save a PyTorch model in .pt format.

    Args:
        model (torch.nn.Module): The PyTorch model to be saved.
        filepath (str): The file path to save the model to.
    """
    torch.save(model.state_dict(), filepath)
    print(f"Model saved to {filepath}.")

def prepare_train(input_seqs, target_seqs, word_to_idx,idx_to_word,config):
    EMBEDDING_DIM = config["embedding_dim"]
    HIDDEN_DIM = config["hidden_dim"]
    BATCH_SIZE = config["batch_size"]
    NUM_EPOCHS = config["num_epochs"]
    NUM_LAYERS = config["num_layers"]
    ACTIVATION = config["activation"]
    encoder = Encoder(len(word_to_idx), EMBEDDING_DIM, HIDDEN_DIM,NUM_LAYERS)
    decoder = Decoder(len(word_to_idx), EMBEDDING_DIM, HIDDEN_DIM,NUM_LAYERS,ACTIVATION)
    encoder_optimizer = optim.Adam(encoder.parameters())
    decoder_optimizer = optim.Adam(decoder.parameters())
    criterion = nn.CrossEntropyLoss()
    encoder = encoder.to(device)
    decoder = decoder.to(device)
    bleu_score_test = -1
    scores =[]
    net_score_train = 0
    for epoch in range(NUM_EPOCHS):
        # random.shuffle(training_data)
        total_loss = 0
        for i in range(0, len(training_data), BATCH_SIZE):
            batch = training_data[i:i+BATCH_SIZE]
            input_seqs = []
            target_seqs = []
            for j in range(len(batch)):
                input_seqs.append( torch.tensor([word_to_idx[word] for word in batch[j][0].split()]).to(device))
                target_seqs.append(torch.tensor([word_to_idx[word] for word in batch[j][1].split()]).to(device))
            loss = train(input_seqs, target_seqs, encoder, decoder, encoder_optimizer, decoder_optimizer, criterion, word_to_idx)
            total_loss += loss
            print("Epoch {} Batch {} Loss: {:.4f}".format(epoch+1, i//BATCH_SIZE, loss))
        translated_sentences = translate_sentence(validation_data, encoder, decoder, word_to_idx, idx_to_word)
        index = ''
        translated_sentences_test = translate_sentence(test_data, encoder, decoder, word_to_idx, idx_to_word)
        score = evaluate(validation_data,translated_sentences,index='')
        score_test = evaluate(test_data,translated_sentences_test,index='')
        if(epoch%30 == 0):
          translated_sentences_train = translate_sentence(training_data, encoder, decoder, word_to_idx, idx_to_word)
          score_train = evaluate(training_data,translated_sentences_train,index='train')
          for i in score_train:
            net_score_train += i
          net_score_train/=len(weights)
          
        net_score = 0
        for i in score:
            net_score += i
        net_score/= len(weights)
        net_score_test = 0
        for i in score_test:
            net_score_test += i
        net_score_test/= len(weights)
        scores.append(score_test)
        if(bleu_score_test<net_score_test):
          bleu_score_test = net_score_test
          save_model(encoder, "./encoder.pt")
          save_model(decoder, "./decoder.pt")
          score = evaluate(validation_data,translated_sentences,index='val')
          score_test = evaluate(test_data,translated_sentences_test,index='test')
        data_to_log={
             "epoch": epoch+1,
            "train_loss": total_loss,
            "bleu_score_train": net_score_train,
            "bleu_score_val": net_score,
            "bleu_score_test": net_score_test,
            "bleu_score_unigram" : score_test[0],
            "bleu_score_bigram" : score_test[1],
            "bleu_score_trigram" : score_test[2],
            "bleu_score_4gram" : score_test[3],
            "bleu_score_5gram" : score_test[4],
            "bleu_score_6gram" : score_test[5],
            "bleu_score_7gram" : score_test[6],
            "bleu_score_8gram" : score_test[7]
        }
        wandb.log(data_to_log)
        print("Epoch {} Total Loss: {:.4f}".format(epoch+1, total_loss),"bleu_socre_val: ",net_score,"bleu_socre_test: ",net_score_test)
    with open('./logs1.txt','w') as f:
      for score in scores:
        score_line = ', '.join([str(s) for s in score])
        f.write(score_line+'\n')
      f.close()
    print(scores)

training_data,validation_data,test_data = prepare_data()
# print(validation_data)
# print(test_data)
# Define the vocabulary
word_to_idx = {START_TOKEN: START_TOKEN_IDX, END_TOKEN: END_TOKEN_IDX, PAD_TOKEN: PAD_TOKEN_IDX,UNK_TOKEN: UNK_TOKEN_IDX}
for sentence_pair in training_data:
    for word in sentence_pair[0].split() + sentence_pair[1].split():
        if word not in word_to_idx:
            word_to_idx[word] = len(word_to_idx)

# add START_TOKEN and END_TOKEN to every sentence in training_data
for i in range(len(training_data)):
    training_data[i] = (START_TOKEN + " " + training_data[i][0] + " " + END_TOKEN, START_TOKEN + " " + training_data[i][1] + " " + END_TOKEN)

# Train the model
# Convert the word_to_idx dictionary to an idx_to_word dictionary for decoding
idx_to_word = {idx: word for word, idx in word_to_idx.items()}
# prepare_train(training_data,validation_data,word_to_idx,encoder, decoder, encoder_optimizer, decoder_optimizer, criterion, idx_to_word)
# prepare_train(training_data,validation_data,word_to_idx, idx_to_word,config)
prepare_train(training_data,validation_data,word_to_idx, idx_to_word,config)
# def sweep_agent_manager():
#     wandb.init()
#     config = dict(wandb.config)
#     print(config)
#     run_name = f"{config['run_type']}_lay_{config['num_layers']}_epo_{config['num_epochs']}_bs_{config['batch_size']}_act_{config['activation']}"
#     wandb.run.name = run_name
#     prepare_train(training_data,validation_data,word_to_idx, idx_to_word,config)
# wandb.agent(sweep_id="lakshmipathi-balaji/inlp-project/4l0jlxjs", function=sweep_agent_manager, count=100)

from nltk.translate.bleu_score import sentence_bleu
weights = [(1, 0, 0, 0), (0.5, 0.5), (0.33, 0.33, 0.33, 0), (0.25, 0.25, 0.25, 0.25),(0.2,0.2,0.2,0.2,0.2),(0.16,0.16,0.16,0.16,0.16,0.16),(0.14,0.14,0.14,0.14,0.14,0.14,0.14),(0.125,0.125,0.125,0.125,0.125,0.125,0.125,0.125)]

def bleu_score(references, candidates):
    score = [0]*len(weights)
    for i in range(len(references)):
        for j,w in enumerate(weights):
            temp_score = sentence_bleu([references[i]], candidates[i], weights=w)
            # print(references[i], candidates[i])
            # add temp score truncated to 2 decimal places to score[j]
            score[j] += temp_score
    for i in range(len(score)):
        score[i] = score[i]/len(references)
        score[i] = round(score[i],6)
    return score
config = {
    "batch_size": 1024,
    "num_epochs": 100,
}

# !pip install wandb
import wandb
wandb.init(entity = "lakshmipathi-balaji",   # wandb username. (NOT REQUIRED ARG. ANYMORE, it fetches from initial login)
           project = "inlp-project", # wandb project name. New project will be created if given project is missing.
           config = config         # Config dict
          )
wandb.run.name = f"seq2seq_transformer_FINAL_1"

# # !pip install pytorch_beam_search
# import torch
# from pytorch_beam_search import seq2seq
# device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# # HYPERPARAMETERS
# # Define the model hyperparameters
# MAX_SENT_LENGTH = 19
# BATCH_SIZE = config["batch_size"]
# NUM_EPOCHS = config["num_epochs"]
# def test(source_test, index):
#     predictions, log_probabilities = seq2seq.beam_search(model, source_test)
#     output = [target_index.tensor2text(p) for p in predictions]
#     # print(len(output))

#     predicted = []
#     actual = []
#     for i in target_test_copy:
#         actual.append(i[0].split())

#     for i in output:
#         text = i[0]
#         text = text.replace("<END>", " ")
#         text = text.replace("<START>", " ")
#         text = text.replace("<UNK>", " ")
#         if len(text.split()) == 0:
#           text = "lkasjdfjaeorjf(not_possible_word)"
#         predicted.append(text.split())
#     if (index=='test'):
#       with open('test_translations_seq2seq_transformer.txt','w') as f:
#         for i in range(len(actual)):
#           ref_line = ' '.join([str(s) for s in actual[i]])
#           cand_line = ' '.join([str(s) for s in predicted[i]])
#           f.write(ref_line+'    '+cand_line+'\n')
#     if (index=='train'):
#       with open('train_translations_seq2seq_transformer.txt','w') as f:
#         for i in range(len(actual)):
#           ref_line = ' '.join([str(s) for s in actual[i]])
#           cand_line = ' '.join([str(s) for s in predicted[i]])
#           f.write(ref_line+'    '+cand_line+'\n')
#     score =  bleu_score(actual,predicted)
#     return score

# # now implement the a model similart to above one for our dataset
# def prepare_data_train():
#     with open('./train1.txt') as f:
#         source = []
#         target = []
#         text = f.read()
#         text = text.split('\n')
#         for line in text:
#             if line:
#                 line = line.split('\t')
#                 a = []
#                 a.append((line[0]))
#                 b = []
#                 b.append((line[1]))
#                 source.append(a)
#                 target.append(b)
#     return (source, target)

# def prepare_data_test():
#     with open('./test1.txt') as f:
#         source = []
#         target = []
#         text = f.read()
#         text = text.split('\n')
#         for line in text:
#             if line:
#                 line = line.split('\t')
#                 a = []
#                 a.append((line[0]))
#                 b = []
#                 b.append((line[1]))
#                 source.append(a)
#                 target.append(b)
#     return (source, target)

# def save_model(model, filepath):
#     """
#     Save a PyTorch model in .pt format.

#     Args:
#         model (torch.nn.Module): The PyTorch model to be saved.
#         filepath (str): The file path to save the model to.
#     """
#     torch.save(model.state_dict(), filepath)
#     print(f"Model saved to {filepath}.")


# f = open("logs.txt", "w")

# (source,target) = prepare_data_train()
# (source_test,target_test) = prepare_data_test()
# target_test_copy = []
# target_test_copy = target_test
# source_index = seq2seq.Index(source)
# target_index = seq2seq.Index(target)
# source_index_for_test = seq2seq.Index(source)
# target_index_for_test = seq2seq.Index(target)
# source_test = source_index.text2tensor(source_test).to(device)
# target_test = target_index.text2tensor(target_test).to(device)
# source_test_of_source = source_index_for_test.text2tensor(source).to(device)
# target_test_of_source = target_index_for_test.text2tensor(target).to(device)

# model = seq2seq.Transformer(source_index, target_index).to(device)
# loss = 0
# error_rate = 0
# net_test_score = 0
# net_score_train = 0
# for epoch in range(NUM_EPOCHS):
#     for i in range(0, len(source), BATCH_SIZE):
#         source_batch = source[i:i+BATCH_SIZE]
#         target_batch = target[i:i+BATCH_SIZE]
#         source_batch = source_index.text2tensor(source_batch).to(device)
#         target_batch = target_index.text2tensor(target_batch).to(device)
#         model.fit(source_batch, target_batch, epochs = 5)
#     loss, error_rate = model.evaluate(source_test, target_test)
#     predictions, log_probabilities = seq2seq.beam_search(model, source_test)
#     log = "Epoch: "+str(epoch) +" Loss: " + str(loss) + " Error Rate: "+ str(error_rate) +"\n"
#     f.write(log)
#     score_test = test(source_test,index = "test")
#     if(epoch%5 == 0):
#       score_train = test(source_test_of_source,index = "train")
#       net_score_train =0 
#       for i in score_train:
#         net_score_train += i
#       net_score_train/= len(weights)

#     net_score_test = 0
#     for i in score_test:
#         net_score_test += i
#     net_score_test/= len(weights)
#     if(net_score_test > net_test_score):
#       net_test_score = net_score_test
#       save_model(model,'./transformer.pt' )
#     print("Epoch: ",epoch,"bleu_score_test: ", net_test_score,"bleu_score_train: ", net_score_train)
#     data_to_log={
#              "epoch": str(epoch),
#             "bleu_score_test": net_score_test,
#             "bleu_score_train": net_score_train,
#             "bleu_score_unigram" : score_test[0],
#             "bleu_score_bigram" : score_test[1],
#             "bleu_score_trigram" : score_test[2],
#             "bleu_score_4gram" : score_test[3],
#             "bleu_score_5gram" : score_test[4],
#             "bleu_score_6gram" : score_test[5],
#             "bleu_score_7gram" : score_test[6],
#             "bleu_score_8gram" : score_test[7]
#         }
#     wandb.log(data_to_log)
# f.close()

# for i in range(len(predicted)):
#   print("##tra##: ",predicted[i])
#   print("#real##: ", actual[i])



"""# Define the model hyperparameters
config = {
    "max_sent_length": 15,
    "embedding_dim": 300,
    "hidden_dim": 512,
    "batch_size": 16,
    "num_epochs": 5,
    "learning_rate": 0.01,
    "num_layers": 2,
    "run_type": "test"
}
"""