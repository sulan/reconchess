#!/usr/bin/env python
import pkg_resources
import argparse
import contextlib
import chess
import chess.pgn
from reconchess import GameHistory

from typing import Optional

# block output from pygame
with contextlib.redirect_stdout(None):
    import pygame

def pgn_loader(fname: str) -> GameHistory:
    try:
        game = chess.pgn.read_game(open(fname, 'r'))
        history = GameHistory()
        history._white_name = game.headers['White']
        history._black_name = game.headers['Black']
        history._win_reason = None # Not applicable
        result = game.headers['Result']
        history._winner_color = (chess.WHITE if result == '1-0'
                            else chess.BLACK if result == '0-1' else None)
        board = game.board()
        for move in game.mainline_moves():
            capture_square = None
            if board.is_capture(move):
                capture_square = move.to_square
            history.store_move(board.turn, move, move, capture_square)
            board.push(move)
            history.store_fen_after_move(not board.turn, board.fen())
        num_white_turns = len(history._taken_moves[chess.WHITE])
        num_black_turns = len(history._taken_moves[chess.BLACK])
        history._senses = {chess.WHITE: [1] * num_white_turns,
                           chess.BLACK: [1] * num_black_turns}
        return history
    except OSError:
        print('Error reading PNG file.')


class Button:
    BUTTON_RECT_COLOR = (238, 238, 238)
    BUTTON_TEXT_COLOR = (0, 0, 0)

    BUTTON_DISABLED_RECT_COLOR = (238, 238, 238)
    BUTTON_DISABLED_TEXT_COLOR = (170, 170, 170)

    BUTTON_HOVER_RECT_COLOR = (224, 224, 224)
    BUTTON_HOVER_TEXT_COLOR = (0, 0, 0)

    BUTTON_DOWN_RECT_COLOR = (200, 200, 200)
    BUTTON_DOWN_TEXT_COLOR = (0, 0, 0)

    def __init__(self, x, y, width, height, font, text, onclick=None):
        self.rect = (x, y, width, height)
        self.text = font.render(text, True, self.BUTTON_TEXT_COLOR)
        self.hover_text = font.render(text, True, self.BUTTON_HOVER_TEXT_COLOR)
        self.down_text = font.render(text, True, self.BUTTON_DOWN_TEXT_COLOR)
        self.disabled_text = font.render(text, True, self.BUTTON_DISABLED_TEXT_COLOR)

        text_width, text_height = font.size(text)
        self.text_position = (x - text_width / 2 + width / 2, y - text_height / 2 + height / 2)

        self.onclick = onclick
        self.enabled = True

        self.is_down = False

    def mouse_is_over(self):
        x, y = pygame.mouse.get_pos()
        return self.rect[0] < x < self.rect[0] + self.rect[2] and self.rect[1] < y < self.rect[1] + self.rect[3]

    def is_hovered(self):
        return pygame.mouse.get_focused() and self.mouse_is_over() and not bool(pygame.mouse.get_pressed()[0])

    def is_pressed(self):
        return pygame.mouse.get_focused() and self.mouse_is_over() and bool(pygame.mouse.get_pressed()[0])

    def update(self):
        released = self.is_down and not self.is_pressed()
        if self.enabled and self.onclick is not None and released:
            self.onclick()
        self.is_down = self.is_pressed()

    def draw(self, background):
        if not self.enabled:
            text = self.disabled_text
            rect_color = self.BUTTON_DISABLED_RECT_COLOR
        elif self.is_hovered():
            text = self.hover_text
            rect_color = self.BUTTON_HOVER_RECT_COLOR
        elif self.is_pressed():
            text = self.down_text
            rect_color = self.BUTTON_DOWN_RECT_COLOR
        else:
            text = self.text
            rect_color = self.BUTTON_RECT_COLOR

        pygame.draw.rect(background, rect_color, self.rect)
        background.blit(text, self.text_position)


class ReplayWindow:
    LIGHT_COLOR = (240, 217, 181)
    DARK_COLOR = (181, 136, 99)

    CAPTURE_COLOR = (255, 0, 0)

    LIGHT_SQUARES = list(chess.SquareSet(chess.BB_LIGHT_SQUARES))
    DARK_SQUARES = list(chess.SquareSet(chess.BB_DARK_SQUARES))

    def __init__(self, history: GameHistory, draw_pieces: str = 'both',
                 automatic_advance: Optional[int] = None):
        self.actions = []
        for turn in history.turns():
            # if history.has_sense(turn):
            #     self.actions.append({
            #         'phase': 'sense',
            #         'turn_number': turn.turn_number,
            #         'turn_color': turn.color,
            #         'sense': history.sense(turn),
            #         'sense_result': history.sense_result(turn),
            #         'fen': history.truth_fen_before_move(turn) if history.is_first_turn(
            #             turn) else history.truth_fen_after_move(turn.previous),
            #     })
            if history.has_move(turn):
                self.actions.append({
                    'phase': 'move',
                    'turn_number': turn.turn_number,
                    'turn_color': turn.color,
                    'requested_move': history.requested_move(turn),
                    'taken_move': history.taken_move(turn),
                    'capture_square': history.capture_square(turn),
                    'fen': history.truth_fen_after_move(turn),
                })

        self.player_names = [history._white_name, history._black_name]
        self.last_advance = pygame.time.get_ticks()
        self.automatic_advance = automatic_advance

        self.board = chess.Board()
        self.action_index = None

        self.draw_pieces = draw_pieces

        self.fps = 30
        self.square_size = 80
        self.width = self.square_size * 8
        self.height = self.square_size * 9

        self.image_by_piece = {}
        for color in chess.COLORS:
            for piece_type in chess.PIECE_TYPES:
                piece = chess.Piece(piece_type, color)

                img_path = 'res/{}/{}.png'.format(chess.COLOR_NAMES[color], piece.symbol())
                full_path = pkg_resources.resource_filename('reconchess', img_path)

                img = pygame.image.load(full_path)
                img = pygame.transform.scale(img, (self.square_size, self.square_size))
                self.image_by_piece[piece] = img

        pygame.init()
        pygame.display.set_caption('Recon Chess')
        pygame.display.set_icon(
            pygame.transform.scale(self.image_by_piece[chess.Piece(chess.KING, chess.WHITE)], (32, 32)))

        self.clock = pygame.time.Clock()
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.background = pygame.Surface((self.screen.get_size()))

        self.perspective = chess.WHITE

        self.font = pygame.font.SysFont(pygame.font.get_default_font(), 30)
        self.buttons = []

        x, y = self.text_coords_below(chess.C1, vertical_offset = 0.20)
        self.buttons.append(Button(x, y, self.square_size / 2, self.square_size / 4, self.font, '<<',
                                   onclick=self.go_to_beginning))

        x, y = self.text_coords_below(chess.D1, vertical_offset = 0.20)
        self.buttons.append(Button(x, y, self.square_size / 2, self.square_size / 4, self.font, '<',
                                   onclick=self.go_backwards))

        x, y = self.text_coords_below(chess.E1, vertical_offset = 0.20)
        self.buttons.append(Button(x, y, self.square_size / 2, self.square_size / 4, self.font, '>',
                                   onclick=self.go_forwards))

        x, y = self.text_coords_below(chess.F1, vertical_offset = 0.20)
        self.buttons.append(Button(x, y, self.square_size / 2, self.square_size / 4, self.font, '>>',
                                   onclick=self.go_to_end))

        self.go_to_beginning()

    def go_to_beginning(self):
        self.action_index = None
        self.buttons[0].enabled = False
        self.buttons[1].enabled = False
        self.buttons[2].enabled = True
        self.buttons[3].enabled = True

    def go_to_end(self):
        self.action_index = len(self.actions) - 1
        self.buttons[0].enabled = True
        self.buttons[1].enabled = True
        self.buttons[2].enabled = False
        self.buttons[3].enabled = False

    def go_forwards(self):
        if self.action_index is None:
            self.action_index = 0
        else:
            self.action_index += 1
        self.buttons[0].enabled = True
        self.buttons[1].enabled = True
        self.buttons[2].enabled = self.action_index < len(self.actions) - 1
        self.buttons[3].enabled = self.action_index < len(self.actions) - 1

        self.last_advance = pygame.time.get_ticks()

    def go_backwards(self):
        if self.action_index == 0:
            self.action_index = None
        else:
            self.action_index -= 1
        self.buttons[0].enabled = self.action_index is not None
        self.buttons[1].enabled = self.action_index is not None
        self.buttons[2].enabled = True
        self.buttons[3].enabled = True

    def coords_to_square(self, x, y):
        file = (x // self.square_size)
        if self.perspective == chess.WHITE:
            rank = ((self.height - y) // self.square_size)
        else:
            rank = (y // self.square_size)
        return chess.square(file, rank)

    def square_to_coords(self, square):
        rank = chess.square_rank(square)
        file = chess.square_file(square)
        x = file * self.square_size
        if self.perspective == chess.WHITE:
            y = (7 - rank) * self.square_size
        else:
            y = rank * self.square_size
        return x, y

    def square_rect(self, square):
        x, y = self.square_to_coords(square)
        return x, y, self.square_size, self.square_size

    def text_coords_below(self, square, horizontal_offset=0.25, vertical_offset=0.375):
        x, y = self.square_to_coords(square)
        x += horizontal_offset * self.square_size
        y += (1 + vertical_offset) * self.square_size
        return x, y

    def update(self):
        self.clock.tick(self.fps)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                quit()

        for btn in self.buttons:
            btn.update()

        if self.automatic_advance is not None:
            cur_time = pygame.time.get_ticks()
            # Advance if the time is right and it's not the end
            if cur_time - self.last_advance > self.automatic_advance:
                if (self.action_index is None
                         or self.action_index < len(self.actions) - 1):
                    self.go_forwards()
                else:
                    quit()

    def draw(self):
        self.background.fill((238, 238, 238))

        self.draw_board()
        for btn in self.buttons:
            btn.draw(self.background)

        if self.action_index is not None:
            if self.actions[self.action_index]['phase'] == 'sense':
                self.draw_sense()
            else:
                self.draw_move()

        pygame.draw.line(self.background, (170, 170, 170), (0, self.square_size * 8),
                         (self.square_size * 8, self.square_size * 8))

        self.draw_turn_info()

        self.screen.blit(self.background, (0, 0))
        pygame.display.flip()

    def draw_board(self):
        if self.action_index is None:
            self.board.set_fen(chess.STARTING_FEN)
        else:
            self.board.set_fen(self.actions[self.action_index]['fen'])

        for square in chess.SQUARES:
            color = self.LIGHT_COLOR if square in self.LIGHT_SQUARES else self.DARK_COLOR
            pygame.draw.rect(self.background, color, self.square_rect(square))

            piece = self.board.piece_at(square)
            if piece is not None:
                # Can draw this piece if the opposite color is not the (only)
                # one to draw. Always true if self.draw_pieces == 'both'.
                can_draw_piece = (
                    ['black', 'white'][not piece.color] != self.draw_pieces)
                if can_draw_piece:
                    image = self.image_by_piece[piece]
                    self.background.blit(image, self.square_rect(square))

    def draw_sense(self):
        for square, opt_piece in self.actions[self.action_index]['sense_result']:
            self.draw_highlight(square, color=self.turn_color())

    def draw_move(self):
        requested_move = self.actions[self.action_index]['requested_move']
        taken_move = self.actions[self.action_index]['taken_move']
        capture_square = self.actions[self.action_index]['capture_square']

        # Can draw this move if the opposite color is not the (only) one to
        # draw. Always true if self.draw_pieces == 'both'. Opposite color is
        # the one whose turn it is (who will make the *next* move).
        if ['black', 'white'][self.board.turn] == self.draw_pieces:
            return
        if requested_move is not None and taken_move is None:
            self.draw_highlight(requested_move.from_square, color=(255, 0, 0))
            self.draw_highlight(requested_move.to_square, color=(255, 0, 0))
        elif requested_move is not None and taken_move is not None:
            self.draw_highlight(requested_move.from_square, color=self.turn_color())
            self.draw_highlight(requested_move.to_square, color=self.turn_color())
            self.draw_highlight(taken_move.from_square, color=self.turn_color())
            self.draw_highlight(taken_move.to_square, color=self.turn_color())

    def draw_turn_info(self):
        turn = '-' if self.action_index is None else (self.actions[self.action_index]['turn_number'] + 1)
        player = '-' if self.action_index is None else chess.COLOR_NAMES[self.actions[self.action_index]['turn_color']]

        text = 'Turn: {} / {}'.format(turn, self.actions[-1]['turn_number'] + 1)
        text_width, text_height = self.font.size(text)
        x, y = self.text_coords_below(chess.A1, vertical_offset=0.33)
        x, y = (x, y - text_height / 2 + .33)
        self.background.blit(self.font.render(text, True, (0, 0, 0)), (x, y))

        text = 'Player: {}'.format(player)
        text_width, text_height = self.font.size(text)
        x, y = self.text_coords_below(chess.A1, vertical_offset=0.66)
        x, y = (x, y - text_height / 2 + .33)
        self.background.blit(self.font.render(text, True, (0, 0, 0)), (x, y))

        text = '{} vs {}'.format(*self.player_names)
        text_width, text_height = self.font.size(text)
        x, y = self.text_coords_below(chess.C1, vertical_offset = 0.70)
        x, y = (x, y - text_height / 2 + .33)
        self.background.blit(self.font.render(text, True, (0, 0, 0)), (x, y))

    def turn_color(self):
        return (255, 255, 255) if self.actions[self.action_index]['turn_color'] else (0, 0, 0)

    def draw_highlight(self, square, color=(255, 255, 0)):
        pygame.draw.rect(self.background, color, self.square_rect(square), 3)


def main():
    parser = argparse.ArgumentParser(description='Allows you to watch a saved match.')
    parser.add_argument('history_path', help='Path to saved Game History file.')
    parser.add_argument('--draw_pieces', choices = ['white', 'black', 'both'],
                        default = 'both',
                        help = 'Which pieces to draw (default: both)')
    parser.add_argument('--automatic_advance', type = int,
                        help = 'Automatically advance the replay (interval given in milliseconds)')
    args = parser.parse_args()

    if args.history_path.endswith('.pgn'):
        history = pgn_loader(args.history_path)
    else:
        history = GameHistory.from_file(args.history_path)
    if not history.num_turns(chess.WHITE):
        print('Game History is empty.')
        quit()

    window = ReplayWindow(history, args.draw_pieces, args.automatic_advance)

    while True:
        window.update()
        window.draw()


if __name__ == '__main__':
    main()
