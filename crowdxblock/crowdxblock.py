# pylint: disable=line-too-long
# pylint: disable=unused-argument

import ast
import logging
import operator
import pkg_resources
import random

from xblock.core import XBlock
from xblock.fields import Scope, Dict, List
from xblock.fragment import Fragment

log = logging.getLogger(__name__)

class CrowdXBlock(XBlock):
    """
    This is the Crowd Sourced Hinter XBlock. This Xblock seeks to provide students with hints
    that specifically address their mistake. Additionally, the hints that this Xblock shows
    are created by the students themselves. This doc string will probably be edited later.
    """
    # Database of hints. hints are stored as such: {"incorrect_answer": {"hint": rating}}. each key (incorrect answer)
    # has a corresponding dictionary (in which hints are keys and the hints' ratings are the values).
    hint_database = Dict(default={'answer': {'hint': 5}}, scope=Scope.user_state_summary)
    # This is a dictionary of hints that will be used to determine what hints to show a student.
    # flagged hints are not included in this dictionary of hints
    HintsToUse = Dict({}, scope=Scope.user_state)
    # This is a list of incorrect answer submissions made by the student. this list is mostly used for
    # feedback, to find which incorrect answer's hint a student voted on.
    WrongAnswers = List([], scope=Scope.user_state)
    # A dictionary of default hints. default hints will be shown to students when there are no matches with the
    # student's incorrect answer within the hint_database dictionary (i.e. no students have made hints for the
    # particular incorrect answer)
    DefaultHints = Dict(default={'default_hint': 0}, scope=Scope.content)
    # List of which hints from the HintsToUse dictionary have been shown to the student
    # this list is used to prevent the same hint from showing up to a student (if they submit the same incorrect answers
    # multiple times)
    Used = List([], scope=Scope.user_state)
    # This list is used to prevent students from voting multiple times on the same hint during the feedback stage.
    # i believe this will also prevent students from voting again on a particular hint if they were to return to
    # a particular problem later
    Voted = List(default=[], scope=Scope.user_state)
    # This is a dictionary of hints that have been flagged. the keys represent the incorrect answer submission, and the
    # values are the hints the corresponding hints. even if a hint is flagged, if the hint shows up for a different
    # incorrect answer, i believe that the hint will still be able to show for a student
    Flagged = Dict(default={}, scope=Scope.user_state_summary)

    def student_view(self, context=None):
        """
        This view renders the hint view to the students. The HTML has the hints templated 
        in, and most of the remaining functionality is in the JavaScript. 
        """
        html = self.resource_string("static/html/crowdxblock.html")
        frag = Fragment(html.format(self=self))
        frag.add_css(self.resource_string("static/css/crowdxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/crowdxblock.js"))
        frag.initialize_js('CrowdXBlock')
        return frag

    def studio_view(self, context=None):
        """
        This function defines a view for editing the XBlock when embedding it in a course. It will allow
        one to define, for example, which problem the hinter is for. It is unfinished and does not currently
        work.
        """
        html = self.resource_string("static/html/crowdxblockstudio.html")
        frag = Fragment(html.format(self=self))
        frag.add_css(self.resource_string("static/css/crowdxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/crowdxblock.js"))
        frag.initialize_js('CrowdXBlock')
        return frag

    def resource_string(self, path):
        """
        This function is used to get the path of static resources.
        """
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    @XBlock.json_handler
    def get_hint(self, data, suffix=''):
        """
        Returns hints to students. Hints are placed into the HintsToUse dictionary if it is found that they
        are not flagged. Hints with the highest rating are shown to students unless the student has already
        submitted the same incorrect answer previously.

        Args:
          data['submittedanswer']: The string of text that the student submits for a problem.

        returns:
          'HintsToUse': the highest rated hint for an incorrect answer
                        or another random hint for an incorrect answer
                        or 'Sorry, there are no more hints for this answer.' if no more hints exist
        """
        answer = str(data["submittedanswer"])
        answer = answer.lower() # for analyzing the student input string I make it lower case.
        found_equal_sign = 0
        hints_used = 0
        # the string returned by the event problem_graded is very messy and is different
        # for each problem, but after all of the numbers/letters there is an equal sign, after which the
        # student's input is shown. I use the function below to remove everything before the first equal
        # sign and only take the student's actual input.
        if "=" in answer:
            if found_equal_sign == 0:
                found_equal_sign = 1
                eqplace = answer.index("=") + 1
                answer = answer[eqplace:]
        self.find_hints(answer)
        # add hints to the self.HintsToUse dictionary. Will likely be replaced
        # soon by simply looking within the self.hint_database for hints.
        if str(answer) not in self.hint_database:
            # add incorrect answer to hint_database if no precedent exists
            self.hint_database[str(answer)] = {}
            self.HintsToUse.clear()
            self.HintsToUse.update(self.DefaultHints)
        if max(self.HintsToUse.iteritems(), key=operator.itemgetter(1))[0] not in self.Used:
            # choose highest rated hint for the incorrect answer
            if max(self.HintsToUse.iteritems(), key=operator.itemgetter(1))[0] not in self.Flagged.keys():
                self.Used.append(max(self.HintsToUse.iteritems(), key=operator.itemgetter(1))[0])
                return {'HintsToUse': max(self.HintsToUse.iteritems(), key=operator.itemgetter(1))[0]}
        else:
            # choose another random hint for the answer.
            temporary_hints_list = []
            for hint_keys in self.HintsToUse:
                if hint_keys not in self.Used and hint_keys not in self.Flagged:
                    temporary_hints_list.append(str(hint_keys))
            if len(temporary_hints_list) != 0:
                not_used = random.choice(temporary_hints_list)
            else:
                # if there are no more hints left in either the database or defaults
                self.Used.append(str("There are no hints for" + " " + answer))
                return {'HintsToUse': "Sorry, there are no more hints for this answer."}
            self.Used.append(not_used)
            return {'HintsToUse': not_used}

    def find_hints(self, answer):
        """
        This function is used to find all appropriate hints that would be provided for
        an incorrect answer. Flagged hints are not added into the HintsToUse dictionary.

        Args:
          answer: This is equal to answer from get_hint, the answer the student submitted
        """
        hints_exist = 0
        isflagged = []
        self.WrongAnswers.append(str(answer)) # add the student's input to the temporary list, for later use
        for answer_keys in self.hint_database:
            # look through answer keys to find a match with the student's answer, and add
            # the hints that exist for said answer into the HintsToUse dict.
            hints = str(self.hint_database[str(answer_keys)])
            if str(answer_keys) == str(answer):
                self.HintsToUse.clear()
                self.HintsToUse.update(ast.literal_eval(hints))
        for hint_keys in self.HintsToUse:
            for flagged_keys in self.Flagged:
                if str(hint_keys) == str(flagged_keys):
                    isflagged.append(hint_keys)
        for flagged_keys in isflagged:
            # remove flagged keys from the HintsToUse
            del self.HintsToUse[flagged_keys]
        for answer_keys in self.HintsToUse:
            if answer_keys not in self.Used:
                hints_exist = 1
        if hints_exist == 0:
            self.HintsToUse.update(self.DefaultHints)

    @XBlock.json_handler
    def get_feedback(self, data, suffix=''):
        """
        This function is used to facilitate student feedback to hints. Specifically this function
        is used to send necessary data to JS about incorrect answer submissions and hints.

        Returns:
          feedback_data: This dicitonary contains all incorrect answers that a student submitted
                         for the question, all the hints the student recieved, as well as two
                         more random hints that exist for an incorrect answer in the hint_database
        """
        feedback_data = {}
        # feedback_data is a dictionary of hints (or lack thereof) used for a
        # specific answer, as well as 2 other random hints that exist for each answer
        # that were not used. The keys are the used hints, the values are the
        # corresponding incorrect answer
        number_of_hints = 0
        if len(self.WrongAnswers) == 0:
            return
        else:
            for index in range(0, len(self.Used)):
                # each index is a hint that was used, in order of usage
                for answer_keys in self.hint_database:
                    if str(self.Used[index]) in self.hint_database[str(answer_keys)]:
                        # add new key (hint) to feedback_data with a value (incorrect answer)
                        feedback_data[str(self.Used[index])] = str(self.WrongAnswers[index])
                for answer_keys in self.hint_database:
                    if str(answer_keys) == str(self.WrongAnswers[index]):
                        # for answes in self.hint_database, if the len of the answer's corresponding
                        # hints is not zero...
                        if str(len(self.hint_database[str(answer_keys)])) != str(0):
                            number_of_hints = 0
                            hint_key_shuffled = self.hint_database[str(answer_keys)].keys()
                            # shuffle keys so that random hints won't repeat. probably can be done better.
                            random.shuffle(hint_key_shuffled)
                            for random_hint_key in hint_key_shuffled:
                                if str(random_hint_key) not in self.Flagged.keys():
                                    if number_of_hints < 3:
                                        number_of_hints += 1
                                        # add random unused hint to feedback_data's keys
                                        # with the value as the incorrect answer
                                        feedback_data[str(random_hint_key)] = str(self.WrongAnswers[index])
                                        self.WrongAnswers.append(str(self.WrongAnswers[index]))
                                        self.Used.append(str(random_hint_key))
                        else:
                            self.no_hints(index)
                            feedback_data[str("There are no hints for" + " " + str(self.WrongAnswers[index]))] = str(self.WrongAnswers[index])
        self.Used = []
        self.WrongAnswers = []
        return feedback_data

    def no_hints(self, index):
        """
        This function is used when no hints exist for an answer. The feedback_data within
        get_feedback is set to "there are no hints for" + " " + str(self.WrongAnswers[index])
        """
        self.WrongAnswers.append(str(self.WrongAnswers[index]))
        self.Used.append(str("There are no hints for" + " " + str(self.WrongAnswers[index])))

    @XBlock.json_handler
    def rate_hint(self, data, suffix=''):
        """
        Used to facilitate hint rating by students. Ratings are -1, 1, or 0. -1 is downvote, 1 is upvote, and 0 is
        when a student flags a hint. 'zzeerroo' is returned to JS when a hint's rating is 0 because whenever 0 was
        simply returned, JS would interpret it as null.

        Hint ratings in hint_database are updated and the resulting hint rating (or flagged status) is returned to JS.

        Args:
          data['answer']: The incorrect answer that corresponds to the hint that is being voted on
          data['value']: The hint that is being voted on
          data['student_rating']: The rating chosen by the student. The value is -1, 1, or 0.

        Returns:
          "rating": The rating of the hint. 'zzeerroo' is returned if the hint's rating is 0.
                    If the hint has already been voted on, 'You have already voted on this hint!'
                    will be returned to JS.
        """
        original_data = data['answer'] # original strings are saved to return later
        answer_data = data['answer']
        # answer_data is manipulated to remove symbols to prevent errors that
        # might arise due to certain symbols. I don't think I have this fully working but am not sure.
        data_rating = data['student_rating']
        data_value = data['value']
        answer_data = self.remove_symbols(answer_data)
        if str(data['student_rating']) == str(0):
            # if student flagged hint
            self.hint_flagged(data['value'], answer_data)
            return {"rating": 'thiswasflagged', 'origdata': original_data}
        if str(answer_data) not in self.Voted:
            self.Voted.append(str(answer_data)) # add data to Voted to prevent multiple votes
            rating = self.change_rating(data_value, int(data_rating), answer_data) # change hint rating
            if str(rating) == str(0):
                # if the rating is "0", return "zzeerroo" instead. "0" showed up as "null" in JS
                return {"rating": str('zzeerroo'), 'origdata': original_data}
            else:
                return {"rating": str(rating), 'origdata': original_data}
        else:
            return {"rating": str('You have already voted on this hint!'), 'origdata': original_data}

    def hint_flagged(self, data_value, answer_data):
        """
        This is used to add a hint to the self.flagged dictionary. When a hint is returned with the rating
        of 0, it is considered to be flagged.

        Args:
          data_value: This is equal to the data['value'] in self.rate_hint
          answer_data: This is equal to the data['answer'] in self.rate_hint
        """
        for answer_keys in self.hint_database:
            if answer_keys == data_value:
                for hint_keys in self.hint_database[str(answer_keys)]:
                    if str(hint_keys) == answer_data:
                        self.Flagged[str(hint_keys)] = str(answer_keys)

    def change_rating(self, data_value, data_rating, answer_data):
        """
        This function is used to change the rating of a hint when it is voted on.
        Initiated by rate_hint. The temporary_dictionary is manipulated to be used
        in self.rate_hint

        Args:
          data_value: This is equal to the data['value'] in self.rate_hint
          data_rating: This is equal to the data['student_rating'] in self.rate_hint
          answer_data: This is equal to the data['answer'] in self.rate_hint

        Returns:
          The rating associated with the hint is returned. This rating is identical
          to what would be found under self.hint_database[answer_string[hint_string]]
        """
        temporary_dictionary = str(self.hint_database[str(answer_data)])
        temporary_dictionary = (ast.literal_eval(temporary_dictionary))
        temporary_dictionary[str(data_value)] += int(data_rating)
        self.hint_database[str(answer_data)] = temporary_dictionary
        return str(temporary_dictionary[str(data_value)])

    def remove_symbols(self, answer_data):
        """
        For removing colons and such from answers to prevent weird things from happening. Not sure if this is properly functional.

        Args:
          answer_data: This is equal to the data['answer'] in self.rate_hint

        Returns:
          answer_data: This is equal to the argument answer_data except that symbols have been
                       replaced by text (hopefully)
        """
        answer_data = answer_data.replace('ddeecciimmaallppooiinntt', '.')
        answer_data = answer_data.replace('qquueessttiioonnmmaarrkk', '?')
        answer_data = answer_data.replace('ccoolloonn', ':')
        answer_data = answer_data.replace('sseemmiiccoolloonn', ';')
        answer_data = answer_data.replace('eeqquuaallss', '=')
        answer_data = answer_data.replace('qquuoottaattiioonnmmaarrkkss', '"')
        return answer_data

    @XBlock.json_handler
    def moderate_hint(self, data, suffix=''):
        """
        UNDER CONSTRUCTION, intended to be used for instructors to remove hints from the database after hints
        have been flagged.
        """
        flagged_hints = {}
        flagged_hints = self.Flagged
        if data['rating'] == "dismiss":
            flagged_hints.pop(data['answer_wrong'], None)
        else:
            flagged_hints.pop(data['answer_wrong'], None)
            for answer_keys in self.hint_database:
                if str(answer_keys) == data['answ']:
                    for hint_keys in self.hint_database[str(answer_keys)]:
                        if str(hint_keys) == data['hint']:
                            temporary_dict = str(self.hint_database[str(answer_keys)])
                            temporary_dict = (ast.literal_eval(temporary_dict))
                            temporary_dict.pop(hint_keys, None)
                            self.hint_database[str(answer_keys)] = temporary_dict

    @XBlock.json_handler
    def give_hint(self, data, suffix=''):
        """
        This function adds a new hint submitted by the student into the hint_database.

        Args:
          data['submission']: This is the text of the new hint that the student has submitted.
          data['answer']: This is the incorrect answer for which the student is submitting a new hint.
        """
        submission = data['submission'].replace('ddeecciimmaallppooiinntt', '.')
        answer = data['answer'].replace('ddeecciimmaallppooiinntt', '.')
        for answer_keys in self.hint_database:
            if str(answer_keys) == str(answer):
                # find the answer for which a hint is being submitted
                if str(submission) not in self.hint_database[str(answer_keys)]:
                    temporary_dictionary = str(self.hint_database[str(answer_keys)])
                    temporary_dictionary = (ast.literal_eval(temporary_dictionary))
                    temporary_dictionary.update({submission: 0})
                    # once again, manipulating temporary_dictionary and setting
                    # self.hint_database equal to it due to being unable to directly
                    # edit self.hint_databse. Most likely scope error
                    self.hint_database[str(answer_keys)] = temporary_dictionary
                    return
                else:
                    # if the hint exists already, simply upvote the previously entered hint
                    if str(submission) in self.DefaultHints:
                        self.DefaultHints[str(submission)] += int(1)
                        return
                    else:
                        temporary_dictionary = str(self.hint_database[str(answer)])
                        temporary_dictionary = (ast.literal_eval(temporary_dictionary))
                        temporary_dictionary[str(submission)] += int(data['rating'])
                        self.hint_database[str(answer)] = temporary_dictionary
                        return

    @XBlock.json_handler
    def studiodata(self, data, suffix=''):
        """
        This function serves to return the dictionary of flagged hints to JS. This is intended for use in
        the studio_view, which is under construction at the moment
        """
        return self.Flagged

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("CrowdXBlock",
             """<vertical_demo>
<crowdxblock/>
</vertical_demo>
"""),
        ]
