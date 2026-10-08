from app.skills.context import brief_history, generation_history, relevant_history, retrieval_question


def test_older_relevant_question_and_answer_survive_recent_turn_selection():
    history = [{'role': 'user', 'content': 'Hello'}, {'role': 'assistant', 'content': 'Welcome'}]
    history += [{'role': 'user', 'content': 'Our app is called Orbit Garden and serves teachers.'},
                {'role': 'assistant', 'content': 'Orbit Garden helps teachers.'}]
    history += [{'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Unrelated experiment {i}'} for i in range(40)]
    selected = relevant_history(history, 'What did I say about Orbit Garden?')
    assert history[2] in selected and history[3] in selected
    assert selected[-8:] == history[-8:]
    assert 'Orbit Garden helps teachers' in retrieval_question('What did I say about Orbit Garden?', selected)


def test_long_answers_are_compacted_without_dropping_short_old_user_details():
    history = [{'role': 'user', 'content': 'My app is Orbit Garden.'}]
    history += [{'role': 'assistant', 'content': 'Explanation ' * 1000} for _ in range(20)]
    compact = brief_history(history, budget=6000)
    assert compact[0]['content'] == history[0]['content']
    assert len(compact) == len(history)
    assert len(retrieval_question('How should I improve activation?', history)) <= 12000


def test_named_older_artifact_is_available_in_full_for_editing():
    history = [{'role': 'assistant', 'content': 'Ready', 'skill': 'simple-artifact', 'artifact': {
        'title': 'Tip calculator', 'language': 'html', 'content': '<input id="bill">' + 'x' * 20000}}]
    history += [{'role': 'assistant', 'content': 'Another answer'} for _ in range(10)]
    history += [{'role': 'assistant', 'content': 'Ready', 'skill': 'simple-artifact', 'artifact': {
        'title': 'To-do app', 'language': 'html', 'content': '<ul></ul>'}}]
    context = generation_history(history, 'simple-artifact', 'Add a reset button to the tip calculator.')
    assert context[0]['artifact']['content'] == history[0]['artifact']['content']
    assert 'content' not in context[-1]['artifact']
