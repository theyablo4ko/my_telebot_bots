import websockets
import asyncio
import json
import random

CARDS_MAIN = [['2', 'hearts'], ['2', 'diamonds'], ['2', 'spades'], ['2', 'clubs'],
         ['3', 'hearts'], ['3', 'diamonds'], ['3', 'spades'], ['3', 'clubs'], 
         ['4', 'hearts'], ['4', 'diamonds'], ['4', 'spades'], ['4', 'clubs'], 
         ['5', 'hearts'], ['5', 'diamonds'], ['5', 'spades'], ['5', 'clubs'], 
         ['6', 'hearts'], ['6', 'diamonds'], ['6', 'spades'], ['6', 'clubs'], 
         ['7', 'hearts'], ['7', 'diamonds'], ['7', 'spades'], ['7', 'clubs'], 
         ['8', 'hearts'], ['8', 'diamonds'], ['8', 'spades'], ['8', 'clubs'], 
         ['9', 'hearts'], ['9', 'diamonds'], ['9', 'spades'], ['9', 'clubs'], 
         ['10', 'hearts'], ['10', 'diamonds'], ['10', 'spades'], ['10', 'clubs'], 
         ['J', 'hearts'], ['J', 'diamonds'], ['J', 'spades'], ['J', 'clubs'], 
         ['Q', 'hearts'], ['Q', 'diamonds'], ['Q', 'spades'], ['Q', 'clubs'], 
         ['K', 'hearts'], ['K', 'diamonds'], ['K', 'spades'], ['K', 'clubs'], 
         ['A', 'hearts'], ['A', 'diamonds'], ['A', 'spades'], ['A', 'clubs']]
VALUES = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'10':10,'J':10,'Q':10,'K':10,'A':11}
SUITS = {'hearts':'♥', 'diamonds':'♦', 'spades':'♠', 'clubs':'♣'}
cards_second = CARDS_MAIN
random.shuffle(cards_second)


# def generate_cards(CARDS, num_of_cards):
#     cards_list = []
#     for i in range(num_of_cards):
#         if len(CARDS) != 0:
#             card = CARDS.pop(0)
#             cards_list.append(card)
#     return cards_list
    
